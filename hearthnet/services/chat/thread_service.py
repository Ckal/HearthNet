from __future__ import annotations

import contextlib
import time
import uuid
from typing import Any

from hearthnet.bus.capability import CapabilityDescriptor, RouteRequest
from hearthnet.services.chat.thread_views import ThreadViewStore


class ThreadService:
    """Group-chat thread service.

    Registers:
        chat.thread.create@1.0
        chat.thread.send@1.0
        chat.thread.history@1.0
        chat.thread.invite@1.0
        chat.thread.leave@1.0
    """

    name = "chat.threads"

    def __init__(
        self,
        node_id: str,
        event_log: Any = None,
        bus: Any = None,
        db_path: str | None = None,
    ) -> None:
        self._node_id = node_id
        self._event_log = event_log
        self._bus = bus
        self._store = ThreadViewStore(db_path=db_path)

    # ── Registration ──────────────────────────────────────────────────────────

    def capabilities(self) -> list[tuple]:
        return [
            (
                CapabilityDescriptor(name="chat.thread.create", max_concurrent=4, idempotent=False),
                self.create_thread,
                None,
            ),
            (
                CapabilityDescriptor(name="chat.thread.send", max_concurrent=8, idempotent=False),
                self.send_message,
                None,
            ),
            (
                CapabilityDescriptor(name="chat.thread.history", max_concurrent=8, idempotent=True),
                self.get_history,
                None,
            ),
            (
                CapabilityDescriptor(name="chat.thread.invite", max_concurrent=4, idempotent=True),
                self.invite_member,
                None,
            ),
            (
                CapabilityDescriptor(name="chat.thread.leave", max_concurrent=4, idempotent=False),
                self.leave_thread,
                None,
            ),
        ]

    def register(self, bus: Any) -> None:
        self._bus = bus
        for cap, handler, predicate in self.capabilities():
            bus.register_local(cap, handler, predicate)

    # ── Handlers ──────────────────────────────────────────────────────────────

    async def create_thread(self, req: RouteRequest) -> dict:
        params: dict = req.body.get("input", {})
        name: str = params.get("name", "")
        members: list[str] = list(params.get("members", []))
        e2e_enabled: bool = bool(params.get("e2e_enabled", False))

        caller = req.caller or self._node_id
        if caller not in members:
            members.append(caller)

        thread_id = f"thread:{uuid.uuid4().hex}"
        created_at = time.time()

        event = {
            "event_id": f"evt:{uuid.uuid4().hex}",
            "event_type": "chat.thread.created",
            "author": caller,
            "payload": {
                "thread_id": thread_id,
                "name": name,
                "members": members,
                "created_at": created_at,
                "e2e_enabled": e2e_enabled,
            },
        }

        if self._event_log is not None:
            try:
                logged = self._event_log.append_local(
                    event_type="chat.thread.created",
                    author=caller,
                    payload=event["payload"],
                )
                self._store.apply(
                    {
                        "event_id": logged.event_id,
                        "event_type": "chat.thread.created",
                        "author": caller,
                        "payload": event["payload"],
                    }
                )
            except Exception:
                self._store.apply(event)
        else:
            self._store.apply(event)

        return {"output": {"thread_id": thread_id, "created_at": created_at}, "meta": {}}

    async def send_message(self, req: RouteRequest) -> dict:
        params: dict = req.body.get("input", {})
        thread_id: str | None = params.get("thread_id")
        content: str = params.get("content", "")
        caller = req.caller or self._node_id

        if not thread_id:
            return {"error": "bad_request", "message": "thread_id required"}
        if not content:
            return {"error": "bad_request", "message": "content required"}

        # Verify thread exists and caller is a member
        thread = self._store.get_thread(thread_id)
        if thread is None:
            return {"error": "not_found", "message": f"thread {thread_id} not found"}
        if caller not in thread.members:
            return {"error": "forbidden", "message": "not a member of this thread"}

        event_id = f"msg:{uuid.uuid4().hex}"
        sent_at = time.time()

        event = {
            "event_id": event_id,
            "event_type": "chat.thread.message.sent",
            "author": caller,
            "payload": {
                "thread_id": thread_id,
                "sender": caller,
                "content": content,
                "sent_at": sent_at,
            },
        }

        if self._event_log is not None:
            try:
                logged = self._event_log.append_local(
                    event_type="chat.thread.message.sent",
                    author=caller,
                    payload=event["payload"],
                )
                self._store.apply(
                    {
                        "event_id": logged.event_id,
                        "event_type": "chat.thread.message.sent",
                        "author": caller,
                        "payload": event["payload"],
                    }
                )
                event_id = logged.event_id
            except Exception:
                self._store.apply(event)
        else:
            self._store.apply(event)

        return {"output": {"event_id": event_id, "sent_at": sent_at}, "meta": {}}

    async def get_history(self, req: RouteRequest) -> dict:
        params: dict = req.body.get("input", {})
        thread_id: str | None = params.get("thread_id")
        since: float | None = params.get("since")
        limit: int = int(params.get("limit", 50))
        caller = req.caller or self._node_id

        if not thread_id:
            return {"error": "bad_request", "message": "thread_id required"}

        thread = self._store.get_thread(thread_id)
        if thread is None:
            return {"error": "not_found", "message": f"thread {thread_id} not found"}
        if caller not in thread.members:
            return {"error": "forbidden", "message": "not a member of this thread"}

        messages = self._store.get_messages(thread_id, since=since, limit=limit)
        return {
            "output": {
                "messages": [
                    {
                        "event_id": m.event_id,
                        "thread_id": m.thread_id,
                        "sender": m.sender,
                        "content": m.content,
                        "sent_at": m.sent_at,
                        "delivered_to": list(m.delivered_to),
                    }
                    for m in messages
                ]
            },
            "meta": {},
        }

    async def invite_member(self, req: RouteRequest) -> dict:
        params: dict = req.body.get("input", {})
        thread_id: str | None = params.get("thread_id")
        member_id: str | None = params.get("member_id")
        caller = req.caller or self._node_id

        if not thread_id or not member_id:
            return {"error": "bad_request", "message": "thread_id and member_id required"}

        thread = self._store.get_thread(thread_id)
        if thread is None:
            return {"error": "not_found", "message": f"thread {thread_id} not found"}
        if caller not in thread.members:
            return {"error": "forbidden", "message": "not a member of this thread"}

        event = {
            "event_id": f"evt:{uuid.uuid4().hex}",
            "event_type": "chat.thread.member.added",
            "author": caller,
            "payload": {"thread_id": thread_id, "member_id": member_id},
        }

        if self._event_log is not None:
            with contextlib.suppress(Exception):
                self._event_log.append_local(
                    event_type="chat.thread.member.added",
                    author=caller,
                    payload=event["payload"],
                )

        self._store.apply(event)
        return {"output": {"success": True}, "meta": {}}

    async def leave_thread(self, req: RouteRequest) -> dict:
        params: dict = req.body.get("input", {})
        thread_id: str | None = params.get("thread_id")
        caller = req.caller or self._node_id

        if not thread_id:
            return {"error": "bad_request", "message": "thread_id required"}

        thread = self._store.get_thread(thread_id)
        if thread is None:
            return {"error": "not_found", "message": f"thread {thread_id} not found"}
        if caller not in thread.members:
            return {"error": "forbidden", "message": "not a member of this thread"}

        event = {
            "event_id": f"evt:{uuid.uuid4().hex}",
            "event_type": "chat.thread.member.removed",
            "author": caller,
            "payload": {"thread_id": thread_id, "member_id": caller},
        }

        if self._event_log is not None:
            with contextlib.suppress(Exception):
                self._event_log.append_local(
                    event_type="chat.thread.member.removed",
                    author=caller,
                    payload=event["payload"],
                )

        self._store.apply(event)
        return {"output": {"success": True}, "meta": {}}
