from __future__ import annotations

import asyncio
import time

from hearthnet.services.rerank.backends.base import (
    RerankedDoc,
    RerankRequest,
    RerankResponse,
)


class BgeRerankerBackend:
    """Cross-encoder reranker using BAAI/bge-reranker models."""

    name = "bge_reranker"

    def __init__(
        self,
        model_id: str = "BAAI/bge-reranker-v2-m3",
        device: str = "auto",
        max_batch: int = 32,
    ) -> None:
        self._model_id = model_id
        self._device = device
        self._max_batch = max_batch
        self._encoder = None
        self._loaded = False
        self._load_error: str | None = None

    def _load(self) -> bool:
        if self._loaded:
            return True
        if self._load_error:
            return False
        try:
            import torch  # type: ignore[import-untyped]
            from sentence_transformers import CrossEncoder  # type: ignore[import-untyped]

            device = self._device
            if device == "auto":
                device = "cuda" if torch.cuda.is_available() else "cpu"

            self._encoder = CrossEncoder(self._model_id, device=device)
            self._device = device
            self._loaded = True
            return True
        except ImportError as exc:
            self._load_error = f"sentence_transformers not installed: {exc}"
            return False
        except Exception as exc:
            self._load_error = str(exc)
            return False

    async def rerank(self, request: RerankRequest) -> RerankResponse:
        if not self._load():
            return RerankResponse(
                ranked=[RerankedDoc(id=d.id, score=0.0) for d in request.docs],
                meta={"error": self._load_error, "backend": self.name},
            )

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, self._sync_rerank, request)
        return result

    def _sync_rerank(self, request: RerankRequest) -> RerankResponse:
        t0 = time.monotonic()
        pairs = [[request.query, doc.text] for doc in request.docs]
        scores: list[float] = []

        # Process in batches
        for i in range(0, len(pairs), self._max_batch):
            batch = pairs[i : i + self._max_batch]
            batch_scores = self._encoder.predict(batch)  # type: ignore[union-attr]
            scores.extend(float(s) for s in batch_scores)

        ranked = sorted(
            [
                RerankedDoc(id=doc.id, score=score)
                for doc, score in zip(request.docs, scores, strict=False)
            ],
            key=lambda x: x.score,
            reverse=True,
        )
        if request.top_k is not None:
            ranked = ranked[: request.top_k]

        return RerankResponse(
            ranked=ranked,
            meta={
                "backend": self.name,
                "model": self._model_id,
                "ms": int((time.monotonic() - t0) * 1000),
                "doc_count": len(request.docs),
            },
        )

    def health(self) -> dict:
        return {
            "backend": self.name,
            "model": self._model_id,
            "loaded": self._loaded,
            "available": self._load_error is None,
            "error": self._load_error,
        }
