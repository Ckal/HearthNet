"""X01 - FastAPI HTTP Transport Server.

Spec: docs/X01-transport.md §3
Impl-ref: impl_ref.md §4

Endpoints:
  POST /bus/v1/call          - signed capability RPC
  GET  /manifest             - node manifest
  GET  /community/manifest   - community manifest
  GET  /sync/v1/heads        - event log heads
  POST /sync/v1/events       - receive events from peers
  GET  /pubsub/v1/subscribe  - SSE pub-sub stream
  GET  /ws/pubsub/v1/{topic} - WebSocket pub-sub
  GET  /health               - liveness
  GET  /ready                - readiness
  GET  /metrics              - Prometheus metrics
  GET  /trace/recent         - recent bus traces
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timezone
UTC = timezone.utc
from typing import Any

try:
    import uvicorn
    from fastapi import FastAPI, HTTPException, Request, Response
    from fastapi.responses import JSONResponse, StreamingResponse

    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False


def _iso_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_version(version_str: str) -> tuple[int, int]:
    parts = version_str.split(".")
    if len(parts) < 2:
        parts.append("0")
    return (int(parts[0]), int(parts[1]))


class HttpServer:
    def __init__(
        self,
        bus=None,
        node_manifest_fn: Callable[[], dict] | None = None,
        community_manifest_fn: Callable[[], dict] | None = None,
        sync_server=None,
        trace_ring=None,
        blob_store=None,
        host: str = "0.0.0.0",  # nosec B104 â€” binding to all interfaces is intentional for a LAN-serving node
        port: int = 7080,
    ):
        self._bus = bus
        self._node_manifest_fn = node_manifest_fn
        self._community_manifest_fn = community_manifest_fn
        self._sync_server = sync_server
        self._trace_ring = trace_ring
        self._blob_store = blob_store
        self._host = host
        self._port = port
        self._server_task: asyncio.Task | None = None
        self._uvicorn_server = None
        self._app = None
        self._ws_pubsub: Any = None  # WebsocketPubSub, lazy-initialised

    def build_app(self) -> Any:
        """Build and return the FastAPI application."""
        if not HAS_FASTAPI:
            raise ImportError(
                "fastapi and uvicorn are required for HttpServer. "
                "Install them with: pip install fastapi uvicorn"
            )

        app = FastAPI(title="HearthNet")

        @app.get("/health")
        async def health():
            return JSONResponse({"status": "ok", "ts": _iso_now()})

        @app.get("/ready")
        async def ready():
            if self._bus is not None:
                try:
                    caps = self._bus.list_capabilities()
                    if caps:
                        return JSONResponse({"status": "ready"})
                except Exception:
                    pass
            raise HTTPException(status_code=503, detail="not_ready")

        @app.get("/manifest")
        async def manifest():
            if self._node_manifest_fn is not None:
                try:
                    return JSONResponse(self._node_manifest_fn())
                except Exception as exc:
                    return JSONResponse(
                        {"error": "manifest_error", "message": str(exc)}, status_code=500
                    )
            return JSONResponse({"error": "no_manifest"})

        @app.get("/community/manifest")
        async def community_manifest():
            if self._community_manifest_fn is not None:
                try:
                    return JSONResponse(self._community_manifest_fn())
                except Exception as exc:
                    return JSONResponse(
                        {"error": "manifest_error", "message": str(exc)}, status_code=500
                    )
            return JSONResponse({"error": "no_manifest"})

        @app.get("/bus/v1/capabilities")
        async def list_capabilities():
            if self._bus is None:
                return JSONResponse([])
            try:
                caps = self._bus.list_capabilities()
                return JSONResponse(caps if isinstance(caps, list) else list(caps))
            except Exception as exc:
                return JSONResponse({"error": "bus_error", "message": str(exc)}, status_code=500)

        @app.post("/bus/v1/call")
        async def bus_call(request: Request):
            if self._bus is None:
                return JSONResponse(
                    {"error": "no_bus", "message": "bus not configured"}, status_code=503
                )
            try:
                body = await request.json()
            except Exception as _exc:
                raise HTTPException(status_code=400, detail="invalid_json") from _exc

            capability = body.get("capability")
            version_str = body.get("version", "1.0")
            params = body.get("params", {})
            input_data = body.get("input", {})
            stream = body.get("stream", False)

            if not capability:
                return JSONResponse(
                    {"error": "missing_capability", "message": "capability field required"},
                    status_code=400,
                )

            try:
                version_tuple = _parse_version(version_str)
            except (ValueError, TypeError) as exc:
                return JSONResponse(
                    {"error": "invalid_version", "message": str(exc)}, status_code=400
                )

            call_body = {"params": params, "input": input_data}

            if stream:
                from hearthnet.transport.streams import encode_sse_frame

                async def _stream_gen():
                    try:
                        result = self._bus.call(capability, version_tuple, call_body)
                        if hasattr(result, "__aiter__"):
                            async for chunk in result:
                                yield encode_sse_frame(chunk)
                        elif asyncio.iscoroutine(result):
                            data = await result
                            yield encode_sse_frame(data)
                            yield encode_sse_frame({"done": True}, event="done")
                        else:
                            yield encode_sse_frame(result)
                            yield encode_sse_frame({"done": True}, event="done")
                    except Exception as exc:
                        yield encode_sse_frame(
                            {"error": "call_error", "message": str(exc)}, event="error"
                        )

                return StreamingResponse(_stream_gen(), media_type="text/event-stream")

            try:
                result = self._bus.call(capability, version_tuple, call_body)
                if asyncio.iscoroutine(result):
                    result = await result
                return JSONResponse(result)
            except Exception as exc:
                return JSONResponse({"error": "call_error", "message": str(exc)}, status_code=500)

        @app.get("/trace/recent")
        async def trace_recent(n: int = 20):
            if self._trace_ring is None:
                return JSONResponse([])
            try:
                traces = self._trace_ring.recent(n)
                return JSONResponse(traces if isinstance(traces, list) else list(traces))
            except Exception as exc:
                return JSONResponse({"error": "trace_error", "message": str(exc)}, status_code=500)

        @app.get("/metrics")
        async def metrics():
            try:
                from hearthnet.observability.metrics import get_prometheus_text

                text = get_prometheus_text()
                return Response(content=text, media_type="text/plain; version=0.0.4")
            except ImportError:
                return Response(content="# metrics not available\n", media_type="text/plain")
            except Exception as exc:
                return Response(content=f"# error: {exc}\n", media_type="text/plain")

        @app.get("/sync/v1/heads")
        async def sync_heads():
            if self._sync_server is None:
                return JSONResponse({"error": "no_sync"})
            try:
                heads = self._sync_server.heads()
                if asyncio.iscoroutine(heads):
                    heads = await heads
                return JSONResponse(heads)
            except Exception as exc:
                return JSONResponse({"error": "sync_error", "message": str(exc)}, status_code=500)

        @app.post("/sync/v1/events")
        async def sync_events(request: Request):
            if self._sync_server is None:
                return JSONResponse({"error": "no_sync"}, status_code=503)
            try:
                body = await request.json()
                result = self._sync_server.serve_events(body)
                if asyncio.iscoroutine(result):
                    result = await result
                return JSONResponse(result if result is not None else {"ok": True})
            except Exception as exc:
                return JSONResponse({"error": "sync_error", "message": str(exc)}, status_code=500)

        @app.get("/file/chunks/{chunk_cid}")
        async def serve_chunk(chunk_cid: str):
            if self._blob_store is None:
                raise HTTPException(status_code=503, detail="no_blob_store")
            try:
                chunk_bytes = self._blob_store.get_chunk(chunk_cid)
                if asyncio.iscoroutine(chunk_bytes):
                    chunk_bytes = await chunk_bytes
                if chunk_bytes is None:
                    raise HTTPException(status_code=404, detail="chunk_not_found")
                return Response(content=chunk_bytes, media_type="application/octet-stream")
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(status_code=500, detail=str(exc)) from exc

        # ── Mobile PWA static routes (M08 / M22) ─────────────────────────────
        try:
            from hearthnet.ui.mobile.static import (
                PWA_MANIFEST_JSON,
                SERVICE_WORKER_JS,
                build_mobile_html,
            )

            @app.get("/mobile/manifest.json")
            async def mobile_manifest():
                return Response(content=PWA_MANIFEST_JSON, media_type="application/manifest+json")

            @app.get("/mobile/sw.js")
            async def mobile_sw():
                return Response(content=SERVICE_WORKER_JS, media_type="application/javascript")

            @app.get("/mobile/")
            @app.get("/mobile")
            async def mobile_app(request: Request):
                node_url = str(request.base_url).rstrip("/")
                html = build_mobile_html(node_url=node_url)
                return Response(content=html, media_type="text/html")

        except ImportError:
            pass  # mobile static not available

        # â”€â”€ WebSocket pubsub endpoint (X06) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        # Lazy import keeps websocket.py optional â€” server still works without it.
        try:
            from fastapi import WebSocket as _WS
            from starlette.websockets import WebSocketDisconnect as _WSDisc

            from hearthnet.transport.websocket import (
                WebsocketPubSub,
                WebSocketSession,
            )

            if self._ws_pubsub is None:
                self._ws_pubsub = WebsocketPubSub()

            _pubsub = self._ws_pubsub

            @app.websocket("/pubsub/v1/ws/{topic}")
            async def ws_pubsub(websocket: _WS, topic: str):
                await websocket.accept()
                session = WebSocketSession(websocket)
                _pubsub.subscribe(topic, session)
                try:
                    while True:
                        frame = await session.receive_frame()
                        if frame is None:
                            break
                        # Acknowledge ACK frames; ignore others silently
                        if frame.type == "ack":
                            up_to = frame.data.get("upto", 0)
                            await session.send_ack(up_to)
                except _WSDisc:
                    pass
                except Exception:
                    pass
                finally:
                    _pubsub.unsubscribe(topic, session)
                    await session.close()

        except ImportError:
            pass  # websockets / starlette WS not available; endpoint not registered

        self._app = app
        return app

    async def publish_event(self, topic: str, event: str, data: dict) -> int:
        """
        Fan-out *event*/*data* to all WebSocket sessions subscribed to *topic*.

        Returns the number of sessions that received the message.
        Returns 0 if the WebSocket pubsub is not initialised.
        """
        if self._ws_pubsub is None:
            return 0
        try:
            return await self._ws_pubsub.publish(topic, event, data)
        except Exception as exc:
            import logging as _logging

            _logging.getLogger(__name__).warning("HttpServer.publish_event error: %s", exc)
            return 0

    async def start(self) -> None:
        """Start uvicorn in background task."""
        if not HAS_FASTAPI:
            raise ImportError(
                "fastapi and uvicorn are required for HttpServer. "
                "Install them with: pip install fastapi uvicorn"
            )
        if self._app is None:
            self.build_app()

        config = uvicorn.Config(
            app=self._app,
            host=self._host,
            port=self._port,
            log_level="warning",
        )
        self._uvicorn_server = uvicorn.Server(config)
        self._server_task = asyncio.create_task(self._uvicorn_server.serve())

    async def shutdown(self) -> None:
        """Stop uvicorn."""
        if self._uvicorn_server is not None:
            self._uvicorn_server.should_exit = True
        if self._server_task is not None:
            try:
                await asyncio.wait_for(self._server_task, timeout=5.0)
            except (TimeoutError, asyncio.CancelledError):
                self._server_task.cancel()
            finally:
                self._server_task = None
                self._uvicorn_server = None
