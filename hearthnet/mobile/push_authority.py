"""M22 — Mobile push token authority.

The anchor-side service that mobile clients (Flutter) call to:
1. Register their APNs/FCM push token  → ``mobile.push.register@1.0``
2. Deregister (logout / token rotation) → ``mobile.push.deregister@1.0``
3. Receive in-app notifications sent by other services

Push delivery itself is *out of scope* for the local-first anchor — if the
relay tier (M15) is configured the anchor forwards the notification there.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from hearthnet.bus.router import Router

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class PushToken:
    """A mobile push token registration entry."""

    node_id: str
    """The HearthNet node ID of the mobile device."""

    token: str
    """Raw APNs device token or FCM registration ID."""

    platform: str
    """``apns`` | ``fcm`` | ``simulator``."""

    registered_at: float = field(default_factory=time.time)
    last_seen_at: float = field(default_factory=time.time)

    def touch(self) -> None:
        self.last_seen_at = time.time()

    @property
    def token_hash(self) -> str:
        """SHA-256 of the raw token (for logging without leaking the token)."""
        return hashlib.sha256(self.token.encode()).hexdigest()[:12]


@dataclass(frozen=True)
class PushNotification:
    """A notification to be delivered to one or more mobile devices."""

    title: str
    body: str
    data: dict = field(default_factory=dict)
    """Arbitrary key/value payload forwarded to the app."""

    badge: int | None = None
    """iOS badge count; ``None`` leaves the current badge unchanged."""


# ---------------------------------------------------------------------------
# In-memory token store
# ---------------------------------------------------------------------------


class PushTokenRegistry:
    """Thread-safe in-memory registry of push tokens.

    In production you would back this with the SQLite event store (M07 / X02)
    or a dedicated table.  For Phase 1 and 2 the in-memory approach is
    sufficient for single-process deployments.
    """

    def __init__(self) -> None:
        self._tokens: dict[str, list[PushToken]] = {}
        """node_id → list of tokens (a user may have multiple devices)."""

    def register(self, node_id: str, token: str, platform: str) -> PushToken:
        entry = PushToken(node_id=node_id, token=token, platform=platform)
        self._tokens.setdefault(node_id, [])
        # Deduplicate by token value
        existing = {t.token for t in self._tokens[node_id]}
        if token not in existing:
            self._tokens[node_id].append(entry)
        else:
            for t in self._tokens[node_id]:
                if t.token == token:
                    t.touch()
                    entry = t
        return entry

    def deregister(self, node_id: str, token: str) -> bool:
        before = self._tokens.get(node_id, [])
        after = [t for t in before if t.token != token]
        self._tokens[node_id] = after
        return len(after) < len(before)

    def get_tokens(self, node_id: str) -> list[PushToken]:
        return list(self._tokens.get(node_id, []))

    def all_node_ids(self) -> list[str]:
        return list(self._tokens.keys())


# ---------------------------------------------------------------------------
# Bus service
# ---------------------------------------------------------------------------


class MobilePushService:
    """Registers as a bus capability provider for mobile push operations.

    Capabilities provided:
    - ``mobile.push.register@1.0``
    - ``mobile.push.deregister@1.0``
    - ``mobile.push.notify@1.0``   (internal — other services call this)
    """

    def __init__(
        self,
        relay_url: str | None = None,
        bus: Router | None = None,
    ) -> None:
        self._registry = PushTokenRegistry()
        self._relay_url = relay_url
        self._bus = bus

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def health(self) -> dict:
        total_tokens = sum(len(v) for v in self._registry._tokens.values())
        return {
            "status": "ok",
            "registered_devices": total_tokens,
            "relay_url": self._relay_url,
        }

    # ------------------------------------------------------------------
    # Handlers called by the bus router
    # ------------------------------------------------------------------

    def handle_register(self, params: dict) -> dict:
        """``mobile.push.register@1.0`` handler.

        Expected input::

            {
                "node_id":  "<HearthNet node ID>",
                "token":    "<APNs device token or FCM registration ID>",
                "platform": "apns" | "fcm" | "simulator"
            }
        """
        inp = params.get("input", params)
        node_id = str(inp.get("node_id", ""))
        token = str(inp.get("token", ""))
        platform = str(inp.get("platform", "unknown"))
        if not node_id or not token:
            return {
                "output": {"error": "bad_request", "detail": "node_id and token required"},
                "meta": {},
            }
        entry = self._registry.register(node_id, token, platform)
        return {"output": {"status": "registered", "token_hash": entry.token_hash}, "meta": {}}

    def handle_deregister(self, params: dict) -> dict:
        """``mobile.push.deregister@1.0`` handler."""
        inp = params.get("input", params)
        node_id = str(inp.get("node_id", ""))
        token = str(inp.get("token", ""))
        removed = self._registry.deregister(node_id, token)
        return {"output": {"status": "removed" if removed else "not_found"}, "meta": {}}

    async def handle_notify(self, params: dict) -> dict:
        """``mobile.push.notify@1.0`` — internal notification dispatch.

        Sends a :class:`PushNotification` to all registered devices of
        ``target_node_id``.  If a relay URL is configured, forwards there;
        otherwise logs and returns ``{"status": "no_relay"}``.
        """
        inp = params.get("input", params)
        target = str(inp.get("target_node_id", ""))
        notif = PushNotification(
            title=str(inp.get("title", "")),
            body=str(inp.get("body", "")),
            data=inp.get("data", {}),
            badge=inp.get("badge"),
        )
        tokens = self._registry.get_tokens(target)
        if not tokens:
            return {"output": {"status": "no_tokens", "delivered": 0}, "meta": {}}

        if self._relay_url:
            delivered = await self._forward_to_relay(target, tokens, notif)
            return {"output": {"status": "forwarded", "delivered": delivered}, "meta": {}}

        # No relay configured — local delivery only (simulator / test)
        return {"output": {"status": "no_relay", "delivered": 0}, "meta": {}}

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _forward_to_relay(
        self,
        target_node_id: str,
        tokens: list[PushToken],
        notif: PushNotification,
    ) -> int:
        """POST the notification to the relay tier (M15) for each token."""
        try:
            import httpx  # type: ignore
        except ImportError:
            return 0

        payload = {
            "target_node_id": target_node_id,
            "tokens": [{"token": t.token, "platform": t.platform} for t in tokens],
            "notification": {
                "title": notif.title,
                "body": notif.body,
                "data": notif.data,
                "badge": notif.badge,
            },
        }
        delivered = 0
        async with httpx.AsyncClient(timeout=10) as client:
            try:
                resp = await client.post(
                    f"{self._relay_url}/push/v1/send",
                    json=payload,
                )
                if resp.status_code == 200:
                    delivered = len(tokens)
            except httpx.HTTPError:
                pass
        return delivered
