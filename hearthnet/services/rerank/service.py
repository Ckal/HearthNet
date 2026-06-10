from __future__ import annotations

from typing import Any

from hearthnet.bus.capability import CapabilityDescriptor, RouteRequest
from hearthnet.constants import RERANK_MAX_DOCS
from hearthnet.services.rerank.backends.base import (
    RerankBackend,
    RerankDoc,
    RerankRequest,
    RerankResponse,
    RerankedDoc,
)


class RerankService:
    """Service that exposes reranking via the capability bus.

    Registers: rerank.text@1.0
    """

    name = "rerank"

    def __init__(
        self,
        backends: list[RerankBackend] | None = None,
        bus: Any = None,
    ) -> None:
        if backends is not None:
            self._backends: list[RerankBackend] = backends
        else:
            # Lazy-load defaults; failures are graceful
            self._backends = self._default_backends()
        self._bus = bus
        self._by_name: dict[str, RerankBackend] = {b.name: b for b in self._backends}

    @staticmethod
    def _default_backends() -> list[RerankBackend]:
        backends: list[RerankBackend] = []
        try:
            from hearthnet.services.rerank.backends.bge import BgeRerankerBackend
            backends.append(BgeRerankerBackend())
        except Exception:
            pass
        try:
            from hearthnet.services.rerank.backends.cross_encoder import CrossEncoderBackend
            backends.append(CrossEncoderBackend())
        except Exception:
            pass
        return backends

    # ── Service registration ──────────────────────────────────────────────────

    def capabilities(self) -> list[tuple]:
        return [
            (
                CapabilityDescriptor(
                    name="rerank.text",
                    max_concurrent=4,
                    idempotent=True,
                    timeout_seconds=30,
                ),
                self.rerank_text,
                None,
            ),
        ]

    def register(self, bus: Any) -> None:
        self._bus = bus
        for cap, handler, predicate in self.capabilities():
            bus.register_local(cap, handler, predicate)

    # ── Handler ───────────────────────────────────────────────────────────────

    async def rerank_text(self, req: RouteRequest) -> dict:
        params: dict = req.body.get("input", {})

        query: str | None = params.get("query")
        if not query:
            return {"error": "bad_request", "message": "query required"}

        raw_docs: list[dict] = params.get("docs", [])
        if not raw_docs:
            return {"error": "bad_request", "message": "docs required"}

        if len(raw_docs) > RERANK_MAX_DOCS:
            return {
                "error": "bad_request",
                "message": f"docs exceeds limit of {RERANK_MAX_DOCS}",
            }

        docs = [RerankDoc(id=d.get("id", str(i)), text=d.get("text", "")) for i, d in enumerate(raw_docs)]

        top_k: int | None = params.get("top_k")
        model: str | None = params.get("model")

        # Select backend
        backend: RerankBackend | None = None
        if model:
            backend = self._by_name.get(model)
            if backend is None:
                return {"error": "bad_request", "message": f"unknown backend: {model}"}
        elif self._backends:
            backend = self._backends[0]
        else:
            # Fallback: return docs sorted by order with score=0
            ranked = [{"id": d.id, "score": 0.0} for d in docs]
            if top_k is not None:
                ranked = ranked[:top_k]
            return {
                "output": {"ranked": ranked, "meta": {"backend": "none", "warning": "no reranker available"}},
                "meta": {},
            }

        rerank_req = RerankRequest(query=query, docs=docs, top_k=top_k)
        resp: RerankResponse = await backend.rerank(rerank_req)

        return {
            "output": {
                "ranked": [{"id": r.id, "score": r.score} for r in resp.ranked],
                "meta": resp.meta,
            },
            "meta": {},
        }

    def health(self) -> dict:
        return {
            "service": self.name,
            "backends": [b.health() for b in self._backends],
            "available": len(self._backends) > 0,
        }
