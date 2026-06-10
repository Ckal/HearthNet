from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from hearthnet.bus.capability import CapabilityDescriptor, RouteRequest
from hearthnet.constants import MARKET_DEFAULT_TTL_SECONDS
from hearthnet.services.marketplace.views import MarketplaceView


class MarketplaceService:
    name = "marketplace"
    version = "1.0"

    def __init__(self, event_log=None, node_id: str = "") -> None:
        self._event_log = event_log  # optional X02 EventLog
        self._node_id = node_id
        self._view = MarketplaceView()
        self._sweep_task = None
        self._posts_demo: list[dict] = []

    @property
    def posts(self) -> list[dict]:
        """Backward-compatible access to demo-mode post list."""
        return self._posts_demo

    def capabilities(self) -> list[tuple]:
        return [
            (
                CapabilityDescriptor(name="market.post", max_concurrent=4, idempotent=True),
                self.handle_post,
                None,
            ),
            (
                CapabilityDescriptor(name="market.list", max_concurrent=8, idempotent=True),
                self.handle_list,
                None,
            ),
            (
                CapabilityDescriptor(name="market.expire", max_concurrent=4, idempotent=True),
                self.handle_expire,
                None,
            ),
            (
                CapabilityDescriptor(name="market.search", max_concurrent=4, idempotent=True),
                self.handle_search,
                None,
            ),
            (
                CapabilityDescriptor(name="market.delete", max_concurrent=4),
                self.handle_expire,   # delete = immediate expire
                None,
            ),
        ]

    async def handle_post(self, req: RouteRequest) -> dict:
        payload = dict(req.body.get("input", {}))
        event_id = payload.get("event_id") or f"evt:{uuid.uuid4().hex}"
        payload.setdefault("client_id", event_id)
        payload.setdefault("author", req.caller)
        payload.setdefault("created_at", _iso_now())
        payload.setdefault("expires_at", _iso_after(MARKET_DEFAULT_TTL_SECONDS))
        payload.setdefault("category", "info")

        if self._event_log is not None:
            try:
                event = self._event_log.append_local(
                    event_type="market.post.created",
                    author=req.caller,
                    payload=payload,
                )
                self._view.apply(event)
                return {
                    "output": {"event_id": event.event_id, "lamport": event.lamport},
                    "meta": {},
                }
            except Exception:
                pass  # fall through to demo mode

        # Demo mode (no event log)
        payload["event_id"] = event_id
        payload["lamport"] = len(self._posts_demo) + 1
        self._posts_demo.append(payload)
        return {"output": {"event_id": event_id, "lamport": len(self._posts_demo)}, "meta": {}}

    async def handle_list(self, req: RouteRequest) -> dict:
        category = req.body.get("input", {}).get("category")

        if self._event_log is not None:
            posts = self._view.all_active()
            result = [p.as_dict() for p in posts if not category or p.category == category]
        else:
            result = [p for p in self._posts_demo if not category or p.get("category") == category]

        return {"output": {"posts": result, "max_lamport": len(result)}, "meta": {}}

    async def handle_expire(self, req: RouteRequest) -> dict:
        inp = req.body.get("input", {})
        target_event_id = inp.get("event_id", "")

        if self._event_log is not None:
            try:
                event = self._event_log.append_local(
                    event_type="market.post.expired",
                    author=req.caller,
                    payload={
                        "target_event_id": target_event_id,
                        "reason": inp.get("reason", "manual"),
                    },
                )
                self._view.apply(event)
                return {"output": {"expired": True, "event_id": target_event_id}, "meta": {}}
            except Exception:
                pass

        # Demo mode
        self._posts_demo = [p for p in self._posts_demo if p.get("event_id") != target_event_id]
        return {"output": {"expired": True, "event_id": target_event_id}, "meta": {}}

    async def handle_search(self, req: RouteRequest) -> dict:
        query = req.body.get("input", {}).get("query", "").lower()

        if self._event_log is not None:
            posts = self._view.all_active()
            result = [
                p.as_dict() for p in posts if query in p.title.lower() or query in p.body.lower()
            ]
            return {"output": {"posts": result}, "meta": {}}

        # Demo mode
        result = [
            p
            for p in self._posts_demo
            if query in p.get("title", "").lower() or query in p.get("body", "").lower()
        ]
        return {"output": {"posts": result}, "meta": {}}


def _iso_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _iso_after(seconds: int) -> str:
    return (datetime.now(UTC) + timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")
