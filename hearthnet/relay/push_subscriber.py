"""Push token registry for relay-mediated mobile notifications (M15)."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)

try:
    import httpx

    HAS_HTTPX = True
except ImportError:
    httpx = None  # type: ignore[assignment]
    HAS_HTTPX = False


@dataclass
class PushTokenRecord:
    """Record of a mobile push token registered with a relay."""

    node_id: str
    platform: str  # "apns" | "fcm" | "generic"
    device_token: str
    relay_url: str
    registered_at: float


class PushSubscriber:
    """
    Registers and unregisters APNs / FCM device tokens with a relay server.

    Degrades gracefully when the relay is unreachable.
    """

    def __init__(
        self,
        relay_url: str,
        http_client: object | None = None,
    ) -> None:
        self._relay_url = relay_url.rstrip("/")
        self._http_client = http_client
        self._httpx_client: object | None = None

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _get_httpx(self) -> object:
        if not HAS_HTTPX:
            raise ImportError("httpx is required for PushSubscriber: pip install httpx")
        if self._httpx_client is None:
            import httpx as _httpx

            self._httpx_client = _httpx.AsyncClient(timeout=10.0)
        return self._httpx_client

    async def _post(self, path: str, body: dict) -> dict | None:
        url = f"{self._relay_url}{path}"
        try:
            client = self._get_httpx()
            resp = await client.post(url, json=body)  # type: ignore[union-attr]
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning("PushSubscriber POST %s failed: %s", path, exc)
            return None

    # ── Public API ────────────────────────────────────────────────────────────

    async def register_push_token(
        self,
        node_id: str,
        platform: str,
        device_token: str,
    ) -> bool:
        """
        Register a mobile push token with the relay.

        Returns True on success, False on failure.
        """
        payload = {
            "node_id": node_id,
            "platform": platform,
            "device_token": device_token,
            "registered_at": time.time(),
        }
        data = await self._post("/relay/v1/push/register", payload)
        return bool(data and data.get("ok"))

    async def unregister(self, node_id: str, device_token: str) -> bool:
        """
        Remove a push token registration from the relay.

        Returns True on success, False on failure.
        """
        payload = {"node_id": node_id, "device_token": device_token}
        data = await self._post("/relay/v1/push/unregister", payload)
        return bool(data and data.get("ok"))

    async def close(self) -> None:
        """Close the internal httpx client."""
        from contextlib import suppress
        if self._httpx_client is not None:
            with suppress(Exception):
                await self._httpx_client.aclose()  # type: ignore[union-attr]
            self._httpx_client = None
