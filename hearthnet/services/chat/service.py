from __future__ import annotations

import uuid
from datetime import datetime, timezone

from hearthnet.bus.capability import CapabilityDescriptor, RouteRequest

UTC = timezone.utc
from hearthnet.services.chat.delivery import DeliveryManager
from hearthnet.services.chat.views import ChatView


class ChatService:
    name = "chat"
    version = "1.0"

    def __init__(self, node_id: str, event_log=None, bus=None) -> None:
        self._node_id = node_id
        self._event_log = event_log
        self._bus = bus
        self._view = ChatView(node_id)
        self._delivery = DeliveryManager(bus=bus, our_node_id=node_id)
        # Backward compat: in-memory messages list
        self.messages: list[dict] = []

    def capabilities(self) -> list[tuple]:
        return [
            (
                CapabilityDescriptor(name="chat.send", max_concurrent=8, idempotent=True),
                self.send,
                None,
            ),
            (
                CapabilityDescriptor(name="chat.history", max_concurrent=8, idempotent=True),
                self.history,
                None,
            ),
            (
                CapabilityDescriptor(name="chat.deliver", max_concurrent=8, idempotent=True),
                self.deliver,
                None,
            ),
        ]

    async def send(self, req: RouteRequest) -> dict:
        payload = dict(req.body.get("input", {}))

        if not payload.get("recipient") and not payload.get("to"):
            return {"error": "bad_request", "message": "recipient required"}

        recipient = payload.get("recipient") or payload.get("to", "")

        if recipient == self._node_id:
            return {"error": "bad_request", "message": "Cannot send to self"}

        event_id = payload.get("event_id") or f"msg:{uuid.uuid4().hex}"
        client_id = payload.get("client_id", event_id)
        now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

        msg_payload = {
            "to": recipient,
            "body": payload.get("body", ""),
            "attachments": payload.get("attachments", []),
            "sent_at": now,
            "client_id": client_id,
        }

        if self._event_log is not None:
            try:
                event = self._event_log.append_local(
                    event_type="chat.message.sent",
                    author=req.caller or self._node_id,
                    payload=msg_payload,
                )
                self._view.apply(event)
                message = {
                    "event_id": event.event_id,
                    "from": req.caller or self._node_id,
                    "to": recipient,
                    "body": payload.get("body", ""),
                    "attachments": payload.get("attachments", []),
                    "sent_at": now,
                    "client_id": client_id,
                }
                delivered = await self._deliver_remote(message)
                return {
                    "output": {
                        "event_id": event.event_id,
                        "lamport": event.lamport,
                        "delivered": delivered,
                    },
                    "meta": {},
                }
            except Exception:
                pass

        # Demo / backward-compat mode
        message = {
            "event_id": event_id,
            "from": req.caller or self._node_id,
            "to": recipient,
            "body": payload.get("body", ""),
            "attachments": payload.get("attachments", []),
            "sent_at": now,
            "client_id": client_id,
        }
        self.messages.append(message)
        delivered = await self._deliver_remote(message)
        return {
            "output": {
                "event_id": event_id,
                "lamport": len(self.messages),
                "delivered": delivered,
            },
            "meta": {},
        }

    async def _deliver_remote(self, message: dict) -> str:
        """Push *message* to the recipient node over the transport.

        Returns ``"delivered"`` when the recipient node acknowledges receipt,
        else ``"queued"`` (store-and-forward — recipient offline/unreachable).
        """
        recipient = message.get("to", "")
        if not recipient or recipient == self._node_id:
            return "direct"
        bus = self._bus
        if bus is None or getattr(bus, "transport", None) is None:
            return "queued"
        try:
            inbound = RouteRequest(
                capability="chat.deliver",
                version_req=(1, 0),
                body={"input": dict(message)},
                caller=self._node_id,
                trace_id=uuid.uuid4().hex,
            )
            result = await bus.transport.call(recipient, inbound)
            if result.get("output", {}).get("status") == "received":
                return "delivered"
            return "queued"
        except Exception:
            return "queued"

    async def deliver(self, req: RouteRequest) -> dict:
        """Inbound delivery from a peer — materialise into our local chat log.

        Stores into both the backward-compat ``messages`` list and the
        event-sourced :class:`ChatView` so :meth:`history` returns the message
        regardless of which mode this node runs in. Idempotent on ``event_id``.
        """
        payload = dict(req.body.get("input", {}))
        event_id = payload.get("event_id") or f"msg:{uuid.uuid4().hex}"
        from_node = payload.get("from") or req.caller or ""
        to_node = payload.get("to") or self._node_id

        if any(m.get("event_id") == event_id for m in self.messages):
            return {"output": {"status": "received", "event_id": event_id}, "meta": {}}

        message = {
            "event_id": event_id,
            "from": from_node,
            "to": to_node,
            "body": payload.get("body", ""),
            "attachments": payload.get("attachments", []),
        }
        self.messages.append(message)
        self._view.apply(
            {
                "event_type": "chat.message.sent",
                "event_id": event_id,
                "author": from_node,
                "payload": {
                    "to": to_node,
                    "body": payload.get("body", ""),
                    "attachments": payload.get("attachments", []),
                    "sent_at": payload.get("sent_at", ""),
                    "client_id": payload.get("client_id", event_id),
                },
            }
        )
        return {"output": {"status": "received", "event_id": event_id}, "meta": {}}

    async def history(self, req: RouteRequest) -> dict:
        peer = req.body.get("input", {}).get("peer")

        if self._event_log is not None:
            if peer:
                msgs = [m.as_dict() for m in self._view.messages_with(peer)]
            else:
                msgs = [m.as_dict() for m in self._view.all_messages()]
        else:
            msgs = [
                m
                for m in self.messages
                if peer is None or m.get("from") == peer or m.get("to") == peer
            ]

        return {"output": {"messages": msgs}, "meta": {}}
