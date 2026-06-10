from __future__ import annotations

from hearthnet.services.rerank.backends.bge import BgeRerankerBackend
from hearthnet.services.rerank.backends.base import RerankRequest, RerankResponse, RerankedDoc


class CrossEncoderBackend(BgeRerankerBackend):
    """Cross-encoder reranker using ms-marco-MiniLM model."""

    name = "cross_encoder"

    def __init__(
        self,
        model_id: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
        device: str = "auto",
        max_batch: int = 32,
    ) -> None:
        super().__init__(model_id=model_id, device=device, max_batch=max_batch)

    def health(self) -> dict:
        h = super().health()
        h["backend"] = self.name
        return h
