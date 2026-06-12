"""WebSocket upgrade for bidirectional streaming (X06)."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# Optional websockets import (client-side only)
try:
    import websockets  # type: ignore[import]

    HAS_WEBSOCKETS = True
except ImportError:
    websockets = None  # type: ignore[assignment]
    HAS_WEBSOCKETS = False

# Optional FastAPI/Starlette WebSocket import (server-side)
WebSocket: Any
WebSocketDisconnect: Any
WebSocketState: Any

try:
    from starlette.websockets import (  # type: ignore[import]
        WebSocket,
        WebSocketDisconnect,
        WebSocketState,
    )

    HAS_STARLETTE_WS = True
except ImportError:
    WebSocket = None  # type: ignore[assignment]
    WebSocketDisconnect = None  # type: ignore[assignment]
    WebSocketState = None  # type: ignore[assignment]
    HAS_STARLETTE_WS = False


# ── Dataclasses ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class WsClientFrame:
    """A parsed frame received from a WebSocket client."""

    type: str  # "ack" | "tool_result" | "cancel"
    data: dict


# ── Server side ───────────────────────────────────────────────────────────────


class WebSocketSession:
    """Wraps a Starlette/FastAPI WebSocket from the server's perspective."""

    def __init__(self, ws: Any, keypair: Any = None) -> None:
        if ws is None:
            raise ValueError("ws must be a non-None WebSocket object")
        self._ws = ws
        self._keypair = keypair
        self.session_id: str = str(uuid.uuid4())
        self.connected_at: float = time.time()
        self._seq: int = 0

    async def send_event(
        self,
        event: str,
        data: dict,
        seq: int | None = None,
    ) -> None:
        """Send a JSON frame to the client."""
        if seq is None:
            self._seq += 1
            seq = self._seq
        frame = json.dumps({"event": event, "data": data, "seq": seq})
        try:
            await self._ws.send_text(frame)
        except Exception as exc:
            logger.debug("WebSocketSession.send_event error: %s", exc)
            raise

    async def receive_frame(self) -> WsClientFrame | None:
        """Receive and parse one inbound JSON frame. Returns None on disconnect."""
        try:
            raw = await self._ws.receive_text()
        except Exception:
            return None
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("WebSocketSession: malformed JSON from client")
            return None
        frame_type = obj.get("type", "")
        # Strip type key, rest is data
        data = {k: v for k, v in obj.items() if k != "type"}
        return WsClientFrame(type=frame_type, data=data)

    async def send_ack(self, up_to: int) -> None:
        """Send a server-to-client ACK frame."""
        frame = json.dumps({"event": "ack", "data": {"up_to": up_to}, "seq": self._seq})
        try:
            await self._ws.send_text(frame)
        except Exception as exc:
            logger.debug("WebSocketSession.send_ack error: %s", exc)

    async def close(self, code: int = 1000) -> None:
        """Close the WebSocket with the given close code."""
        with contextlib.suppress(Exception):
            await self._ws.close(code=code)


# ── Client side ───────────────────────────────────────────────────────────────


class WebSocketClient:
    """Client-side WebSocket wrapper. Requires the `websockets` library."""

    def __init__(self, base_url: str, keypair: Any = None) -> None:
        if not HAS_WEBSOCKETS:
            raise ImportError("Install websockets: pip install websockets")
        # Convert http(s) to ws(s)
        self._base_url = (
            base_url.rstrip("/").replace("https://", "wss://").replace("http://", "ws://")
        )
        self._keypair = keypair
        self._conn: Any = None  # websockets.WebSocketClientProtocol

    async def connect(self, path: str) -> None:
        """Establish a WebSocket connection to *path* on the server."""
        if not HAS_WEBSOCKETS:
            raise ImportError("Install websockets: pip install websockets")
        url = f"{self._base_url}/{path.lstrip('/')}"
        self._conn = await websockets.connect(url)  # type: ignore[union-attr]

    async def stream(self, event_iterator: Any) -> AsyncIterator[dict]:
        """
        Send frames from *event_iterator* to the server and yield parsed
        server frames until the connection closes.
        """
        if self._conn is None:
            raise RuntimeError("Not connected. Call connect() first.")

        async def _sender() -> None:
            try:
                async for item in event_iterator:
                    await self._conn.send(json.dumps(item))
            except Exception as exc:
                logger.debug("WebSocketClient._sender error: %s", exc)

        sender_task = asyncio.create_task(_sender())
        try:
            async for raw in self._conn:
                try:
                    yield json.loads(raw)
                except json.JSONDecodeError:
                    logger.warning("WebSocketClient: malformed JSON from server")
        finally:
            sender_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await sender_task

    async def send_tool_result(self, tool_call_id: str, body: dict) -> None:
        """Send a tool result frame mid-stream."""
        if self._conn is None:
            raise RuntimeError("Not connected.")
        frame = json.dumps({"type": "tool_result", "tool_call_id": tool_call_id, "body": body})
        await self._conn.send(frame)

    async def cancel(self) -> None:
        """Send a cancel frame to the server."""
        if self._conn is None:
            return
        with contextlib.suppress(Exception):
            await self._conn.send(json.dumps({"type": "cancel"}))

    async def close(self) -> None:
        """Close the WebSocket connection gracefully."""
        if self._conn is not None:
            try:
                await self._conn.close()
            except Exception:
                pass
            finally:
                self._conn = None


# ── PubSub fanout ─────────────────────────────────────────────────────────────


class WebsocketPubSub:
    """
    In-process publish/subscribe for WebSocket sessions.

    subscribe/unsubscribe are synchronous; publish is async and fan-outs to all
    sessions registered for the topic.
    """

    def __init__(self) -> None:
        self._subscriptions: dict[str, set[WebSocketSession]] = {}
        self._lock = asyncio.Lock()

    def subscribe(self, topic: str, ws_session: WebSocketSession) -> None:
        """Register *ws_session* to receive messages on *topic*."""
        if topic not in self._subscriptions:
            self._subscriptions[topic] = set()
        self._subscriptions[topic].add(ws_session)

    def unsubscribe(self, topic: str, ws_session: WebSocketSession) -> None:
        """Remove *ws_session* from *topic*."""
        if topic in self._subscriptions:
            self._subscriptions[topic].discard(ws_session)
            if not self._subscriptions[topic]:
                del self._subscriptions[topic]

    async def publish(self, topic: str, event: str, data: dict) -> int:
        """
        Fan-out *event*/*data* to all sessions subscribed to *topic*.
        Returns the number of sessions that received the message.
        """
        async with self._lock:
            sessions = list(self._subscriptions.get(topic, []))

        dead: list[WebSocketSession] = []
        delivered = 0
        for session in sessions:
            try:
                await session.send_event(event, data)
                delivered += 1
            except Exception:
                dead.append(session)

        # Clean up disconnected sessions
        if dead:
            async with self._lock:
                for session in dead:
                    self.unsubscribe(topic, session)

        return delivered
