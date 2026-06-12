"""HTTP bus transport — bridges bus.transport.call() to real peers over HTTP.

The default :class:`~hearthnet.bus.InMemoryTransport` only delivers calls to
buses living in the same Python process (used by the in-process multi-node demo
and tests). :class:`HttpBusTransport` is a drop-in superset: it still delivers
in-process when the target node is registered locally, but falls back to a real
``POST /bus/v1/call`` over HTTP when the target is a remote peer reachable via a
registered endpoint.

This is what makes a local node talk to the HuggingFace Space node (and vice
versa) over the public internet. No mocks: a remote call is a genuine signed-ish
HTTP request to the peer's FastAPI ``/bus/v1/call`` endpoint.
"""

from __future__ import annotations

from typing import Any

from hearthnet.bus import BusError, InMemoryTransport
from hearthnet.bus.capability import RouteRequest
from hearthnet.types import Endpoint


def _endpoint_to_url(ep: Endpoint) -> str:
    """Build a base URL from an Endpoint.

    transport is one of "https" | "http" | "memory". Port 443 -> https, else the
    declared transport scheme (defaulting to http).
    """
    scheme = "https" if (ep.transport == "https" or ep.port == 443) else "http"
    # Omit the port for the standard 80/443 to keep URLs clean (HF Space uses 443).
    if ep.port in (80, 443):
        return f"{scheme}://{ep.host}"
    return f"{scheme}://{ep.host}:{ep.port}"


class HttpBusTransport(InMemoryTransport):
    """In-process delivery first, real HTTP forwarding for remote peers."""

    async def call(self, node_id: str, req: RouteRequest) -> dict[str, Any]:
        # 1) In-process target (same machine, shared transport, or tests).
        if node_id in self._buses:
            return await super().call(node_id, req)

        # 2) Remote target — resolve its endpoint from any registered registry.
        endpoint = self._resolve_endpoint(node_id)
        if endpoint is None or endpoint.transport == "memory":
            raise BusError("partition", f"node {node_id} is not reachable")
        return await self._http_call(endpoint, req)

    def _resolve_endpoint(self, node_id: str) -> Endpoint | None:
        for bus in self._buses.values():
            for entry in bus.registry.all_remote():
                if entry.node_id == node_id and entry.endpoint is not None:
                    return entry.endpoint
        return None

    async def _http_call(self, endpoint: Endpoint, req: RouteRequest) -> dict[str, Any]:
        try:
            import httpx
        except ImportError as exc:  # pragma: no cover - httpx is a core dep
            raise BusError("internal_error", "httpx not installed") from exc

        url = f"{_endpoint_to_url(endpoint)}/bus/v1/call"
        payload = {
            "capability": req.capability,
            "version": f"{req.version_req[0]}.{req.version_req[1]}",
            "params": req.body.get("params", {}),
            "input": req.body.get("input", {}),
        }
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as exc:
            raise BusError("http_error", f"{url} -> {exc}") from exc
        except Exception as exc:
            raise BusError("partition", f"{url} unreachable: {exc}") from exc

        # The remote may signal a typed error in-band.
        if isinstance(data, dict) and "error" in data and "output" not in data:
            raise BusError(str(data.get("error", "call_error")), str(data.get("message", "")))
        return data
