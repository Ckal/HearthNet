"""Relay client — joins a relay hub, polls its mailbox, and does RPC over it.

This is the NAT-bound counterpart to :mod:`hearthnet.transport.relay_hub`. A local
node that cannot accept inbound connections uses a :class:`RelayClient` to:

1. **join** the hub and register the other members' capabilities locally (so the
   bus can route ``llm.chat`` / ``rag.query`` / ``chat.deliver`` to them);
2. run a background **poll loop** that drains its mailbox and:
   * dispatches inbound ``request`` envelopes to the local bus, then ships the
     ``response`` back through the hub;
   * resolves pending outbound calls when their ``response`` arrives;
   * applies ``roster`` gossip so newly-joined peers become routable (all-to-all);
3. send outbound calls via :meth:`call_remote`, correlating request/response by id.

:class:`RelayStrategy` adapts a :class:`RelayClient` to the
:class:`~hearthnet.bus.transport.DeliveryStrategy` protocol so
:class:`~hearthnet.bus.transport.CompositeTransport` can use it as a fallback.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
import uuid
from typing import Any

from hearthnet.bus import BusError
from hearthnet.bus.capability import RouteRequest
from hearthnet.bus.transport import NOT_HANDLED
from hearthnet.discovery.peers import PeerRecord, PeerRegistry
from hearthnet.types import Endpoint

_log = logging.getLogger(__name__)

# How long an outbound relayed call waits for its response before failing.
RELAY_CALL_TIMEOUT_SECONDS = 30.0


def _parse_version(raw: Any) -> tuple[int, int]:
    parts = str(raw or "1.0").split(".")
    if len(parts) < 2:
        parts.append("0")
    return (int(parts[0]), int(parts[1]))


class RelayClient:
    """Connects a local node to a relay hub for all-to-all messaging over NAT."""

    def __init__(
        self,
        relay_url: str,
        *,
        node_id: str,
        display_name: str,
        community_id: str,
        bus: Any,
        peers: PeerRegistry,
        token: str | None = None,
        poll_timeout: float = 25.0,
    ) -> None:
        self._base = relay_url.rstrip("/")
        self._node_id = node_id
        self._display_name = display_name
        self._community_id = community_id
        self._bus = bus
        self._peers = peers
        self._token = token
        self._poll_timeout = poll_timeout
        self._client: Any = None
        self._members: set[str] = set()
        self._pending: dict[str, asyncio.Future] = {}
        self._poll_task: asyncio.Task | None = None
        self._running = False
        # node_id of the hub's own in-process node, learned from the join
        # response. That node is directly reachable at the relay base URL.
        self._hub_node_id: str | None = None

    @property
    def members(self) -> set[str]:
        return set(self._members)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    async def join(self) -> dict[str, Any]:
        """Join the hub, register the returned roster, and start polling."""
        import httpx

        if self._client is None:
            self._client = httpx.AsyncClient(timeout=60.0)

        caps = sorted({e.descriptor.name for e in self._bus.registry.all_local()})
        payload = {
            "node_id": self._node_id,
            "display_name": self._display_name,
            "community_id": self._community_id,
            "capabilities": caps,
        }
        if self._token:
            payload["token"] = self._token
        resp = await self._client.post(f"{self._base}/relay/v1/join", json=payload)
        resp.raise_for_status()
        data = resp.json()
        if data.get("error"):
            raise BusError(str(data["error"]), str(data.get("message", "")))

        # The hub's own in-process node is directly reachable over HTTP at the
        # relay base URL. Record it so _apply_roster can give it a direct-HTTP
        # endpoint (bypasses the mailbox poll loop, robust across event loops).
        self._hub_node_id = data.get("hub_node_id")
        self._apply_roster(data.get("roster", []))
        self._running = True
        if self._poll_task is None or self._poll_task.done():
            self._poll_task = asyncio.create_task(self._poll_loop(), name="relay-poll")
        return data

    async def close(self) -> None:
        self._running = False
        if self._poll_task is not None:
            self._poll_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._poll_task
            self._poll_task = None
        for fut in self._pending.values():
            if not fut.done():
                fut.cancel()
        self._pending.clear()
        if self._client is not None:
            with contextlib.suppress(Exception):
                await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------
    # Outbound RPC (used by RelayStrategy)
    # ------------------------------------------------------------------
    async def call_remote(self, node_id: str, req: RouteRequest) -> Any:
        """Deliver *req* to *node_id* via the hub and await its response.

        Returns :data:`NOT_HANDLED` if *node_id* is not a known relay member, so
        the composite transport can try other strategies.
        """
        if node_id not in self._members or self._client is None:
            return NOT_HANDLED

        correlation_id = uuid.uuid4().hex
        loop = asyncio.get_event_loop()
        fut: asyncio.Future = loop.create_future()
        self._pending[correlation_id] = fut

        envelope = {
            "kind": "request",
            "from": self._node_id,
            "correlation_id": correlation_id,
            "capability": req.capability,
            "version": f"{req.version_req[0]}.{req.version_req[1]}",
            "body": {"params": req.body.get("params", {}), "input": req.body.get("input", {})},
        }
        try:
            sent = await self._send(node_id, envelope)
        except Exception as exc:
            self._pending.pop(correlation_id, None)
            raise BusError("partition", f"relay send failed: {exc}") from exc
        if sent.get("error"):
            self._pending.pop(correlation_id, None)
            raise BusError(str(sent["error"]), str(sent.get("message", "")))

        try:
            return await asyncio.wait_for(fut, timeout=RELAY_CALL_TIMEOUT_SECONDS)
        except TimeoutError as exc:
            self._pending.pop(correlation_id, None)
            raise BusError("timeout", f"relay call to {node_id} timed out") from exc

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    async def _send(self, to: str, envelope: dict[str, Any]) -> dict[str, Any]:
        resp = await self._client.post(
            f"{self._base}/relay/v1/send", json={"to": to, "envelope": envelope}
        )
        resp.raise_for_status()
        return resp.json()

    async def _poll_loop(self) -> None:
        while self._running:
            try:
                resp = await self._client.get(
                    f"{self._base}/relay/v1/poll",
                    params={"node_id": self._node_id, "timeout": self._poll_timeout},
                )
                resp.raise_for_status()
                data = resp.json()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                _log.debug("relay poll error: %s", exc)
                await asyncio.sleep(2.0)
                continue

            if data.get("error") == "not_joined":
                with contextlib.suppress(Exception):
                    await self.join()
                continue
            for envelope in data.get("envelopes", []):
                await self._handle_envelope(envelope)

    async def _handle_envelope(self, envelope: dict[str, Any]) -> None:
        kind = envelope.get("kind")
        if kind == "request":
            await self._serve_request(envelope)
        elif kind == "response":
            self._resolve_response(envelope)
        elif kind == "roster":
            self._apply_roster(envelope.get("members", []))

    async def _serve_request(self, envelope: dict[str, Any]) -> None:
        from_node = envelope.get("from", "")
        correlation_id = envelope.get("correlation_id", "")
        req = RouteRequest(
            capability=envelope.get("capability", ""),
            version_req=_parse_version(envelope.get("version", "1.0")),
            body=envelope.get("body", {}),
            caller=from_node,
            trace_id=correlation_id or uuid.uuid4().hex,
            deadline_ms=int((time.monotonic() + RELAY_CALL_TIMEOUT_SECONDS) * 1000),
        )
        response: dict[str, Any] = {
            "kind": "response",
            "from": self._node_id,
            "correlation_id": correlation_id,
        }
        try:
            response["result"] = await self._bus.handle_call(req, local_only=True)
        except BusError as exc:
            response["error"] = exc.code
            response["message"] = str(exc)
        except Exception as exc:  # report any handler failure back to the caller
            response["error"] = "internal_error"
            response["message"] = str(exc)
        if from_node:
            with contextlib.suppress(Exception):
                await self._send(from_node, response)

    def _resolve_response(self, envelope: dict[str, Any]) -> None:
        correlation_id = envelope.get("correlation_id", "")
        fut = self._pending.pop(correlation_id, None)
        if fut is None or fut.done():
            return
        if envelope.get("error"):
            fut.set_exception(
                BusError(str(envelope["error"]), str(envelope.get("message", "")))
            )
        else:
            fut.set_result(envelope.get("result", {}))

    def _apply_roster(self, members: list[dict[str, Any]]) -> None:
        for member in members:
            node_id = member.get("node_id")
            if not node_id or node_id == self._node_id:
                continue
            self._members.add(node_id)
            # The hub's own node is directly reachable over HTTP at the relay
            # base URL — give it a direct http/https endpoint so the composite
            # transport's direct-HTTP path serves it via /bus/v1/call. This is
            # robust across event loops (no mailbox poll-loop future needed).
            # All other peers are NAT-bound: mark them with a "relay" endpoint so
            # the direct-HTTP path skips them and the relay strategy delivers.
            if node_id == self._hub_node_id:
                endpoint = self._direct_http_endpoint()
            else:
                endpoint = Endpoint(transport="relay", host=self._base, port=0)
            record = PeerRecord(
                node_id_full=node_id,
                display_name=member.get("display_name", node_id[:20]),
                community_id=member.get("community_id", self._community_id),
                endpoints=[endpoint],
                source="relay",
            )
            self._peers.upsert(record)
            manifest = {
                "node_id": node_id,
                "capabilities": [{"name": name} for name in member.get("capabilities", [])],
            }
            with contextlib.suppress(Exception):
                self._bus.registry.update_from_peer_manifest(record, manifest)

    def _direct_http_endpoint(self) -> Endpoint:
        """Build a direct http/https Endpoint from the relay base URL."""
        from urllib.parse import urlparse

        parsed = urlparse(self._base)
        scheme = parsed.scheme or "https"
        host = parsed.hostname or self._base
        port = parsed.port or (443 if scheme == "https" else 80)
        return Endpoint(transport=scheme, host=host, port=port)




class RelayStrategy:
    """Adapts a :class:`RelayClient` to the bus ``DeliveryStrategy`` protocol."""

    name = "relay"

    def __init__(self, client: RelayClient) -> None:
        self._client = client

    async def try_deliver(self, node_id: str, req: RouteRequest) -> Any:
        return await self._client.call_remote(node_id, req)
