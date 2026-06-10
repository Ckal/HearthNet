from __future__ import annotations

from pathlib import Path
from typing import Any

from hearthnet.bus.capability import CapabilityDescriptor, RouteRequest
from hearthnet.services.rag.store import CorpusStore, list_corpora


class RagService:
    name = "rag"
    version = "1.0"

    def __init__(
        self,
        corpus: str = "default",
        corpora_dir: Path | None = None,
        bus: Any = None,
    ) -> None:
        """bus: optional CapabilityBus for calling embed.text via bus (preferred).
        If bus is None, use SimpleHashBackend directly."""
        self._corpus = corpus
        self._corpora_dir = corpora_dir or Path(".")
        self._bus = bus
        self._store = CorpusStore(self._corpora_dir, corpus)
        self._pipeline = None  # initialized lazily

    def _get_embed_fn(self):
        async def embed_via_bus(texts: list[str]) -> list[list[float]]:
            if self._bus is not None:
                result = await self._bus.call(
                    "embed.text", (1, 0), {"input": {"texts": texts}}
                )
                return result.get("output", {}).get(
                    "embeddings", [[0.0] * 16] * len(texts)
                )
            else:
                from hearthnet.services.embedding.backends import SimpleHashBackend

                backend = SimpleHashBackend()
                return await backend.embed(texts)

        return embed_via_bus

    def capabilities(self) -> list[tuple]:
        return [
            (
                CapabilityDescriptor(
                    name="rag.query",
                    params={"corpus": self._corpus},
                    max_concurrent=4,
                    idempotent=True,
                ),
                self.handle_query,
                self._corpus_matches,
            ),
            (
                CapabilityDescriptor(
                    name="rag.ingest",
                    params={"corpus": self._corpus},
                    trust_required="trusted",
                    idempotent=True,
                ),
                self.handle_ingest,
                self._corpus_matches,
            ),
            (
                CapabilityDescriptor(
                    name="rag.list_corpora",
                    params={},
                    max_concurrent=8,
                    idempotent=True,
                ),
                self.handle_list_corpora,
                None,
            ),
        ]

    def _corpus_matches(self, offered: dict, requested: dict) -> bool:
        return not requested.get("corpus") or requested.get("corpus") == offered.get("corpus")

    async def handle_query(self, req: RouteRequest) -> dict:
        query = req.body.get("input", {}).get("query", "")
        k = int(req.body.get("input", {}).get("k", 5))
        if not query:
            return {"output": {"chunks": []}, "meta": {"corpus": self._corpus}}
        embed_fn = self._get_embed_fn()
        embeddings = await embed_fn([query])
        query_vec = embeddings[0]
        results = self._store.query(query_vec, k=k)
        chunks = [
            {
                "rank": i + 1,
                "score": r.score,
                "text": r.chunk.text,
                "metadata": r.chunk.metadata,
            }
            for i, r in enumerate(results)
        ]
        return {"output": {"chunks": chunks}, "meta": {"corpus": self._corpus}}

    async def handle_ingest(self, req: RouteRequest) -> dict:
        inp = req.body.get("input", {})
        text = inp.get("text", "")
        title = inp.get("title", "Untitled")
        doc_cid = inp.get("doc_cid")
        if not self._pipeline:
            from hearthnet.services.rag.ingest import IngestPipeline

            self._pipeline = IngestPipeline(self._store, self._get_embed_fn())
        result = await self._pipeline.ingest_text(text, title=title, doc_cid=doc_cid)
        return {
            "output": {
                "doc_cid": result.doc_cid,
                "chunks_indexed": result.chunks_indexed,
                "was_duplicate": result.was_duplicate,
            },
            "meta": {"corpus": self._corpus, "ms": result.ms},
        }

    async def handle_list_corpora(self, req: RouteRequest) -> dict:
        names = list_corpora(self._corpora_dir)
        return {"output": {"corpora": names}, "meta": {}}
