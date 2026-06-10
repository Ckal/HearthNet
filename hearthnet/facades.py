from __future__ import annotations

from typing import Any

from hearthnet.bus import CapabilityBus


class RagFacade:
    def __init__(self, bus: CapabilityBus) -> None:
        self.bus = bus

    async def query(self, query: str, *, corpus: str = "demo", k: int = 5) -> dict[str, Any]:
        return await self.bus.call(
            "rag.query", (1, 0), {"params": {"corpus": corpus}, "input": {"query": query, "k": k}}
        )


class ChatFacade:
    def __init__(self, bus: CapabilityBus) -> None:
        self.bus = bus

    async def send(self, recipient: str, body: str) -> dict[str, Any]:
        return await self.bus.call(
            "chat.send", (1, 0), {"params": {}, "input": {"recipient": recipient, "body": body}}
        )


class MarketplaceFacade:
    def __init__(self, bus: CapabilityBus) -> None:
        self.bus = bus

    async def post(self, title: str, body: str, *, category: str = "info") -> dict[str, Any]:
        return await self.bus.call(
            "market.post",
            (1, 0),
            {"params": {}, "input": {"title": title, "body": body, "category": category}},
        )
