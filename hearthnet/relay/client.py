"""Relay client — registers with a relay server for NAT traversal (M15)."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Optional httpx
try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    httpx = None  # type: ignore[assignment]
    HAS_HTTPX = False


@dataclass(frozen=True)
class RelayRegistration:
    """Immutable record of a successful relay registration."""

    relay_url: str
    node_id: str
    registered_at: float
    expires_at: float
    forwarding_url: str


class RelayClient:
    """
    Client-side helper for registering with a HearthNet relay server.

    All methods degrade gracefully when the relay is unreachable: they log a
    warning and return empty / False rather than raising.
    """

    def __init__(
        self,
        relay_url: str,
        http_client: object | None = None,
        keypair: object | None = None,
    ) -> None:
        self._relay_url = relay_url.rstrip("/")
        self._http_client = http_client  # Optional HttpClient instance
        self._keypair = keypair
        self._httpx_client: object | None = None
        self._keepalive_task: asyncio.Task | None = None

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _get_httpx(self) -> object:
        """Return or create a shared httpx.AsyncClient."""
        if not HAS_HTTPX:
            raise ImportError("httpx is required for RelayClient: pip install httpx")
        if self._httpx_client is None:
            import httpx as _httpx  # noqa: PLC0415
            self._httpx_client = _httpx.AsyncClient(timeout=10.0)
        return self._httpx_client

    def _sign_payload(self, payload: dict) -> dict:
        """Attach a signature if a keypair is present."""
        if self._keypair is None:
            return payload
        try:
            if hasattr(self._keypair, "sign"):
                sig = self._keypair.sign(json.dumps(payload, sort_keys=True).encode())
                payload = dict(payload)
                if hasattr(sig, "hex"):
                    payload["_sig"] = sig.hex()
                else:
                    payload["_sig"] = str(sig)
        except Exception as exc:
            logger.debug("RelayClient._sign_payload: %s", exc)
        return payload

    async def _post(self, path: str, body: dict) -> dict | None:
        """POST *body* to relay path. Returns parsed JSON or None on error."""
        url = f"{self._relay_url}{path}"
        try:
            client = self._get_httpx()
            resp = await client.post(url, json=body)  # type: ignore[union-attr]
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning("RelayClient POST %s failed: %s", path, exc)
            return None

    async def _get(self, path: str) -> dict | list | None:
        """GET relay path. Returns parsed JSON or None on error."""
        url = f"{self._relay_url}{path}"
        try:
            client = self._get_httpx()
            resp = await client.get(url)  # type: ignore[union-attr]
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning("RelayClient GET %s failed: %s", path, exc)
            return None

    # ── Public API ────────────────────────────────────────────────────────────

    async def register(
        self,
        node_id: str,
        endpoints: list[str],
        community_id: str,
        ttl: int = 60,
    ) -> RelayRegistration:
        """
        Register this node with the relay server.

        Returns a :class:`RelayRegistration`. On failure, returns a
        registration with ``forwarding_url=""`` and ``expires_at`` in the past.
        """
        now = time.time()
        payload = self._sign_payload(
            {
                "node_id": node_id,
                "endpoints": endpoints,
                "community_id": community_id,
                "ttl": ttl,
                "registered_at": now,
            }
        )
        data = await self._post("/relay/v1/register", payload)
        if data and isinstance(data, dict):
            return RelayRegistration(
                relay_url=self._relay_url,
                node_id=node_id,
                registered_at=now,
                expires_at=data.get("expires_at", now + ttl),
                forwarding_url=data.get("forwarding_url", ""),
            )
        # Degraded: return sentinel with past expiry
        return RelayRegistration(
            relay_url=self._relay_url,
            node_id=node_id,
            registered_at=now,
            expires_at=now - 1,
            forwarding_url="",
        )

    async def heartbeat(self, node_id: str) -> bool:
        """Renew the relay registration. Returns True on success."""
        payload = self._sign_payload({"node_id": node_id, "ts": time.time()})
        data = await self._post("/relay/v1/heartbeat", payload)
        return bool(data and data.get("ok"))

    async def deregister(self, node_id: str) -> bool:
        """Cleanly remove the relay registration. Returns True on success."""
        payload = self._sign_payload({"node_id": node_id})
        data = await self._post("/relay/v1/deregister", payload)
        return bool(data and data.get("ok"))

    async def lookup_community(self, community_id: str) -> list[str]:
        """
        Look up the current bridge endpoint URLs for *community_id*.

        Returns an empty list on error.
        """
        data = await self._get(f"/relay/v1/community/{community_id}")
        if data is None:
            return []
        if isinstance(data, list):
            return [str(e) for e in data]
        if isinstance(data, dict):
            # Accept {"endpoints": [...]} envelope
            return [str(e) for e in data.get("endpoints", [])]
        return []

    async def start_keepalive(
        self,
        node_id: str,
        interval: int = 30,
    ) -> asyncio.Task:
        """
        Start a background asyncio task that sends a heartbeat every
        *interval* seconds.  Cancels any previously running keepalive.
        """
        if self._keepalive_task is not None and not self._keepalive_task.done():
            self._keepalive_task.cancel()

        async def _loop() -> None:
            while True:
                await asyncio.sleep(interval)
                ok = await self.heartbeat(node_id)
                if not ok:
                    logger.warning("RelayClient keepalive heartbeat failed for %s", node_id)

        self._keepalive_task = asyncio.create_task(_loop())
        return self._keepalive_task

    async def close(self) -> None:
        """Cancel keepalive and close the internal httpx client."""
        if self._keepalive_task is not None and not self._keepalive_task.done():
            self._keepalive_task.cancel()
            try:
                await self._keepalive_task
            except asyncio.CancelledError:
                pass
        if self._httpx_client is not None:
            try:
                await self._httpx_client.aclose()  # type: ignore[union-attr]
            except Exception:
                pass
            self._httpx_client = None
