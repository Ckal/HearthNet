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
        event_log: Any = None,
        blob_store: Any = None,
    ) -> None:
        """bus: optional CapabilityBus for calling embed.text via bus (preferred).
        event_log: optional EventLog to emit rag.document.ingested on ingest.
        blob_store: optional BlobStore to persist raw text as BLAKE3 content blob.
        """
        self._corpus = corpus
        self._corpora_dir = corpora_dir or Path(".")
        self._bus = bus
        self._event_log = event_log
        self._blob_store = blob_store
        self._store = CorpusStore(self._corpora_dir, corpus)
        self._pipeline = None  # initialized lazily

    def _get_embed_fn(self):
        async def embed_via_bus(texts: list[str]) -> list[list[float]]:
            if self._bus is not None:
                result = await self._bus.call("embed.text", (1, 0), {"input": {"texts": texts}})
                return result.get("output", {}).get("embeddings", [[0.0] * 16] * len(texts))
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

        # Phase 2: persist raw text as a BLAKE3 content-addressed blob so peers
        # can fetch it via TransferManager (M07/BitTorrent).
        blob_cid: str | None = None
        if not result.was_duplicate and self._blob_store is not None:
            try:
                manifest = self._blob_store.put(text.encode("utf-8"), filename=title)
                blob_cid = manifest.cid
            except Exception:  # noqa: BLE001
                pass

        # Emit rag.document.ingested event so peers learn a new doc exists (X02).
        if not result.was_duplicate and self._event_log is not None:
            try:
                author = (
                    self._bus.node_id_full
                    if self._bus is not None
                    else "unknown"
                )
                payload: dict = {
                    "corpus": self._corpus,
                    "doc_cid": result.doc_cid,
                    "title": title,
                    "chunks_indexed": result.chunks_indexed,
                }
                if blob_cid:
                    payload["blob_cid"] = blob_cid
                self._event_log.append_local(
                    "rag.document.ingested",
                    author,
                    payload,
                )
            except Exception:  # noqa: BLE001
                pass

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
