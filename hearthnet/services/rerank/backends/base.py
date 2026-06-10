from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class RerankDoc:
    id: str
    text: str


@dataclass
class RerankedDoc:
    id: str
    score: float


@dataclass
class RerankRequest:
    query: str
    docs: list[RerankDoc]
    top_k: int | None = None
    params: dict = field(default_factory=dict)


@dataclass
class RerankResponse:
    ranked: list[RerankedDoc]
    meta: dict = field(default_factory=dict)


@runtime_checkable
class RerankBackend(Protocol):
    name: str

    async def rerank(self, request: RerankRequest) -> RerankResponse: ...

    def health(self) -> dict: ...
