from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from hearthnet.bus.capability import CapabilityDescriptor, RouteRequest


def _contains_score(query: str, text: str) -> float:
    terms = {term.lower() for term in query.split() if term.strip()}
    haystack = text.lower()
    if not terms:
        return 0.0
    return sum(1 for term in terms if term in haystack) / len(terms)


@dataclass
class LlmService:
    model: str = "demo-local"
    requires_internet: bool = False
    name: str = "llm"
    version: str = "0.1"

    def capabilities(self) -> list[tuple[Any, ...]]:
        descriptor = CapabilityDescriptor(
            name="llm.chat",
            params={"model": self.model, "requires_internet": self.requires_internet},
            max_concurrent=2,
            idempotent=False,
        )
        return [(descriptor, self.chat, _model_matches)]

    async def chat(self, req: RouteRequest) -> dict[str, Any]:
        messages = req.body.get("input", {}).get("messages", [])
        last = next(
            (msg.get("content", "") for msg in reversed(messages) if msg.get("role") == "user"), ""
        )
        return {
            "output": {"message": {"role": "assistant", "content": f"{self.model}: {last}"}},
            "meta": {
                "model": self.model,
                "tokens_in": len(last.split()),
                "tokens_out": len(last.split()) + 1,
            },
        }


@dataclass
class RagService:
    corpus: str = "demo"
    documents: list[dict[str, Any]] = field(default_factory=list)
    name: str = "rag"
    version: str = "0.1"

    def capabilities(self) -> list[tuple[Any, ...]]:
        return [
            (
                CapabilityDescriptor(
                    name="rag.query", params={"corpus": self.corpus}, max_concurrent=4
                ),
                self.query,
                _corpus_matches,
            ),
            (
                CapabilityDescriptor(
                    name="rag.ingest", params={"corpus": self.corpus}, trust_required="trusted"
                ),
                self.ingest,
            ),
        ]

    async def query(self, req: RouteRequest) -> dict[str, Any]:
        query = req.body.get("input", {}).get("query", "")
        k = int(req.body.get("input", {}).get("k", 5))
        ranked = sorted(
            self.documents, key=lambda doc: _contains_score(query, doc["text"]), reverse=True
        )[:k]
        chunks = [
            {
                "rank": index + 1,
                "score": _contains_score(query, doc["text"]),
                "text": doc["text"],
                "metadata": {"doc_title": doc["title"], "chunk_id": doc["id"]},
            }
            for index, doc in enumerate(ranked)
        ]
        return {"output": {"chunks": chunks}, "meta": {"corpus": self.corpus}}

    async def ingest(self, req: RouteRequest) -> dict[str, Any]:
        payload = req.body.get("input", {})
        doc = {
            "id": payload.get("doc_cid", f"doc:{uuid.uuid4().hex}"),
            "title": payload.get("title", "Untitled"),
            "text": payload.get("text", payload.get("title", "")),
        }
        self.documents.append(doc)
        return {
            "output": {"doc_cid": doc["id"], "chunks_indexed": 1},
            "meta": {"corpus": self.corpus},
        }


@dataclass
class MarketplaceService:
    posts: list[dict[str, Any]] = field(default_factory=list)
    name: str = "marketplace"
    version: str = "0.1"

    def capabilities(self) -> list[tuple[Any, ...]]:
        return [
            (CapabilityDescriptor(name="market.post", max_concurrent=4), self.post),
            (CapabilityDescriptor(name="market.list", max_concurrent=8), self.list_posts),
        ]

    async def post(self, req: RouteRequest) -> dict[str, Any]:
        payload = dict(req.body.get("input", {}))
        payload.setdefault("event_id", uuid.uuid4().hex)
        payload.setdefault("author", req.caller)
        self.posts.append(payload)
        return {"output": {"event_id": payload["event_id"], "lamport": len(self.posts)}, "meta": {}}

    async def list_posts(self, req: RouteRequest) -> dict[str, Any]:
        category = req.body.get("input", {}).get("category")
        posts = [
            post for post in self.posts if category is None or post.get("category") == category
        ]
        return {"output": {"posts": posts, "max_lamport": len(self.posts)}, "meta": {}}


@dataclass
class ChatService:
    node_id: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    name: str = "chat"
    version: str = "0.1"
    bus: Any = None

    def capabilities(self) -> list[tuple[Any, ...]]:
        return [
            (CapabilityDescriptor(name="chat.send", max_concurrent=8, idempotent=True), self.send),
            (
                CapabilityDescriptor(name="chat.history", max_concurrent=8, idempotent=True),
                self.history,
            ),
            (
                CapabilityDescriptor(name="chat.deliver", max_concurrent=8, idempotent=True),
                self.deliver,
            ),
        ]

    async def send(self, req: RouteRequest) -> dict[str, Any]:
        payload = dict(req.body.get("input", {}))
        recipient = payload["recipient"]
        message = {
            "event_id": uuid.uuid4().hex,
            "from": req.caller,
            "to": recipient,
            "body": payload.get("body", ""),
            "attachments": payload.get("attachments", []),
        }
        self.messages.append(message)
        if recipient == self.node_id:
            delivered = "direct"
        else:
            delivered = await self._deliver_remote(recipient, message)
        return {
            "output": {
                "event_id": message["event_id"],
                "lamport": len(self.messages),
                "delivered": delivered,
            },
            "meta": {},
        }

    async def _deliver_remote(self, recipient: str, message: dict[str, Any]) -> str:
        """Push *message* to the recipient node over the transport.

        Returns ``"delivered"`` when the recipient node acknowledges receipt,
        else ``"queued"`` (store-and-forward — the recipient is offline or
        unreachable; the message stays in our local log).
        """
        bus = self.bus
        if bus is None or getattr(bus, "transport", None) is None:
            return "queued"
        try:
            inbound = RouteRequest(
                capability="chat.deliver",
                version_req=(1, 0),
                body={
                    "input": {
                        "event_id": message["event_id"],
                        "from": message["from"],
                        "to": recipient,
                        "body": message["body"],
                        "attachments": message["attachments"],
                    }
                },
                caller=self.node_id,
                trace_id=uuid.uuid4().hex,
            )
            result = await bus.transport.call(recipient, inbound)
            if result.get("output", {}).get("status") == "received":
                return "delivered"
            return "queued"
        except Exception:
            # Recipient offline / unreachable / no chat.deliver — store-and-forward.
            return "queued"

    async def deliver(self, req: RouteRequest) -> dict[str, Any]:
        """Inbound delivery from a peer — append to our local message log."""
        payload = dict(req.body.get("input", {}))
        message = {
            "event_id": payload.get("event_id") or uuid.uuid4().hex,
            "from": payload.get("from", req.caller),
            "to": payload.get("to", self.node_id),
            "body": payload.get("body", ""),
            "attachments": payload.get("attachments", []),
        }
        # Idempotent: ignore duplicates (retried deliveries).
        if any(m["event_id"] == message["event_id"] for m in self.messages):
            return {"output": {"status": "received", "event_id": message["event_id"]}, "meta": {}}
        self.messages.append(message)
        return {"output": {"status": "received", "event_id": message["event_id"]}, "meta": {}}

    async def history(self, req: RouteRequest) -> dict[str, Any]:
        peer = req.body.get("input", {}).get("peer")
        messages = [
            message
            for message in self.messages
            if peer is None or message["from"] == peer or message["to"] == peer
        ]
        return {"output": {"messages": messages}, "meta": {}}


def _model_matches(offered: dict[str, Any], requested: dict[str, Any]) -> bool:
    return not requested.get("model") or requested.get("model") == offered.get("model")


def _corpus_matches(offered: dict[str, Any], requested: dict[str, Any]) -> bool:
    return not requested.get("corpus") or requested.get("corpus") == offered.get("corpus")
