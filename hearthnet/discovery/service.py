"""M02 — Discovery service: manual peer add + peer listing capabilities.

Exposes two bus capabilities used to bridge nodes across networks where mDNS/UDP
multicast cannot reach (e.g. a laptop peering with the public HuggingFace Space):

  discovery.peer.add@1.0   — fetch a peer's /manifest and register its
                             capabilities as routable remote entries
  discovery.peers@1.0      — list currently known peers

``discovery.peer.add`` is the real wiring behind ``scripts/connect_to_hf.py`` and
the Settings "connect to peer" flow. It performs a genuine HTTP GET to the
peer's ``/manifest`` endpoint, then calls
:meth:`Registry.update_from_peer_manifest` so the bus router can dispatch
``llm.chat`` / ``rag.query`` / ``moe.*`` to that peer.
"""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import urlparse

from hearthnet.bus.capability import CapabilityDescriptor, RouteRequest
from hearthnet.discovery.peers import PeerRecord, PeerRegistry
from hearthnet.types import Endpoint


def _parse_endpoint(raw: str) -> Endpoint:
    """Parse a URL or host:port string into an Endpoint."""
    text = raw.strip()
    if "://" not in text:
        text = "http://" + text
    parsed = urlparse(text)
    scheme = parsed.scheme or "http"
    host = parsed.hostname or ""
    port = parsed.port or (443 if scheme == "https" else 80)
    transport = "https" if scheme == "https" else "http"
    return Endpoint(transport=transport, host=host, port=port)


def _endpoint_base_url(ep: Endpoint) -> str:
    scheme = "https" if (ep.transport == "https" or ep.port == 443) else "http"
    if ep.port in (80, 443):
        return f"{scheme}://{ep.host}"
    return f"{scheme}://{ep.host}:{ep.port}"


class DiscoveryService:
    name = "discovery"
    version = "1.0"

    def __init__(self, bus: Any, peers: PeerRegistry) -> None:
        self._bus = bus
        self._peers = peers

    def capabilities(self) -> list[tuple[Any, ...]]:
        return [
            (
                CapabilityDescriptor(
                    name="discovery.peer.add",
                    version=(1, 0),
                    trust_required="trusted",
                    idempotent=False,
                ),
                self.peer_add,
            ),
            (
                CapabilityDescriptor(name="discovery.peers", version=(1, 0)),
                self.peers_list,
            ),
        ]

    async def peer_add(self, req: RouteRequest) -> dict[str, Any]:
        body = req.body.get("input", {}) or req.body.get("params", {})
        raw_endpoint = body.get("endpoint") or body.get("url")
        if not raw_endpoint:
            return {"error": "bad_request", "message": "endpoint is required"}

        endpoint = _parse_endpoint(str(raw_endpoint))
        base = _endpoint_base_url(endpoint)

        manifest = await self._fetch_manifest(base)
        if manifest is None:
            return {
                "error": "partition",
                "message": f"could not fetch manifest from {base}/manifest",
            }

        node_id = manifest.get("node_id") or body.get("node_id") or base
        record = PeerRecord(
            node_id_full=node_id,
            display_name=manifest.get("display_name", body.get("display_name", node_id[:20])),
            community_id=manifest.get("community_id", self._peers.community_id),
            profile=manifest.get("profile", "hearth"),
            endpoints=[endpoint],
            manifest=manifest,
            last_seen=time.monotonic(),
            source="manual",
        )
        self._peers.upsert(record)
        diff = self._bus.registry.update_from_peer_manifest(record, manifest)

        return {
            "output": {
                "node_id": node_id,
                "endpoint": base,
                "capabilities": [e.descriptor.name for e in diff.added],
                "added": len(diff.added),
            }
        }

    async def peers_list(self, req: RouteRequest) -> dict[str, Any]:
        return {"output": {"peers": [p.as_view() for p in self._peers.all()]}}

    async def _fetch_manifest(self, base_url: str) -> dict[str, Any] | None:
        try:
            import httpx
        except ImportError:
            return None
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(f"{base_url}/manifest")
                resp.raise_for_status()
                data = resp.json()
                return data if isinstance(data, dict) and "capabilities" in data else None
        except Exception:
            return None
