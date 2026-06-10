from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ChatMessage:
    event_id: str
    from_node: str
    to_node: str
    body: str
    attachments: list[dict]
    sent_at: str
    delivered_at: str | None
    read_at: str | None
    client_id: str

    def as_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "from": self.from_node,
            "to": self.to_node,
            "body": self.body,
            "attachments": self.attachments,
            "sent_at": self.sent_at,
            "delivered_at": self.delivered_at,
            "read_at": self.read_at,
            "client_id": self.client_id,
        }


class ChatView:
    """MaterialisedView from chat.message.* events."""

    def __init__(self, our_node_id: str) -> None:
        self._our_node_id = our_node_id
        self._messages: dict[str, ChatMessage] = {}  # event_id -> ChatMessage
        self._seen_client_ids: set[str] = set()

    def apply(self, event) -> None:
        etype = getattr(event, "event_type", None) or event.get("event_type", "")
        payload = getattr(event, "payload", None) or event.get("payload", {})
        event_id = getattr(event, "event_id", None) or event.get("event_id", "")
        author = getattr(event, "author", None) or event.get("author", "")

        if etype == "chat.message.sent":
            client_id = payload.get("client_id", event_id)
            if client_id in self._seen_client_ids:
                return
            self._seen_client_ids.add(client_id)
            msg = ChatMessage(
                event_id=event_id,
                from_node=author,
                to_node=payload.get("to", ""),
                body=payload.get("body", ""),
                attachments=payload.get("attachments", []),
                sent_at=payload.get("sent_at", ""),
                delivered_at=None,
                read_at=None,
                client_id=client_id,
            )
            self._messages[event_id] = msg

        elif etype == "chat.message.delivered":
            target_id = payload.get("target_event_id", "")
            if target_id in self._messages:
                old = self._messages[target_id]
                self._messages[target_id] = ChatMessage(
                    event_id=old.event_id,
                    from_node=old.from_node,
                    to_node=old.to_node,
                    body=old.body,
                    attachments=old.attachments,
                    sent_at=old.sent_at,
                    delivered_at=payload.get("delivered_at", ""),
                    read_at=old.read_at,
                    client_id=old.client_id,
                )

        elif etype == "chat.message.read":
            target_id = payload.get("target_event_id", "")
            if target_id in self._messages:
                old = self._messages[target_id]
                self._messages[target_id] = ChatMessage(
                    event_id=old.event_id,
                    from_node=old.from_node,
                    to_node=old.to_node,
                    body=old.body,
                    attachments=old.attachments,
                    sent_at=old.sent_at,
                    delivered_at=old.delivered_at,
                    read_at=payload.get("read_at", ""),
                    client_id=old.client_id,
                )

    def messages_with(self, peer_node_id: str) -> list[ChatMessage]:
        return [
            m for m in self._messages.values()
            if m.from_node == peer_node_id or m.to_node == peer_node_id
        ]

    def all_messages(self) -> list[ChatMessage]:
        return sorted(self._messages.values(), key=lambda m: m.sent_at)

    def unread_count(self, peer: str) -> int:
        return sum(
            1 for m in self._messages.values()
            if m.to_node == self._our_node_id and m.from_node == peer and m.read_at is None
        )

    def snapshot_state(self) -> dict:
        return {
            "messages": {eid: m.as_dict() for eid, m in self._messages.items()},
            "seen_client_ids": list(self._seen_client_ids),
        }

    def restore_state(self, state: dict) -> None:
        self._messages = {}
        for eid, md in state.get("messages", {}).items():
            self._messages[eid] = ChatMessage(
                event_id=md["event_id"],
                from_node=md["from"],
                to_node=md["to"],
                body=md["body"],
                attachments=md.get("attachments", []),
                sent_at=md["sent_at"],
                delivered_at=md.get("delivered_at"),
                read_at=md.get("read_at"),
                client_id=md.get("client_id", eid),
            )
        self._seen_client_ids = set(state.get("seen_client_ids", []))

    def reset(self) -> None:
        self._messages.clear()
        self._seen_client_ids.clear()
