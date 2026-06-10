from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Awaitable, Callable

from hearthnet.services.rag.chunker import Chunk, chunk_pdf, chunk_text
from hearthnet.services.rag.store import CorpusStore


@dataclass(frozen=True)
class IngestResult:
    doc_cid: str
    chunks_indexed: int
    was_duplicate: bool
    ms: int


class IngestPipeline:
    def __init__(
        self,
        store: CorpusStore,
        embed_fn: Callable[[list[str]], Awaitable[list[list[float]]]],
    ) -> None:
        """embed_fn: async callable (texts: list[str]) -> list[list[float]]"""
        self._store = store
        self._embed_fn = embed_fn

    async def ingest_text(
        self,
        text: str,
        *,
        title: str = "Untitled",
        doc_cid: str | None = None,
        page: int = 0,
    ) -> IngestResult:
        t0 = time.monotonic()
        if doc_cid is None:
            doc_cid = "sha256:" + hashlib.sha256(text.encode()).hexdigest()
        if self._store.has_doc(doc_cid):
            return IngestResult(doc_cid=doc_cid, chunks_indexed=0, was_duplicate=True, ms=0)
        chunks = chunk_text(
            text,
            metadata={
                "doc_cid": doc_cid,
                "doc_title": title,
                "page": page,
                "chunk_index": 0,
                "language": "unknown",
            },
        )
        chunks = [
            Chunk(text=c.text, metadata={**c.metadata, "chunk_index": i})
            for i, c in enumerate(chunks)
        ]
        texts = [c.text for c in chunks]
        embeddings = await self._embed_fn(texts)
        self._store.add(chunks, embeddings)
        ms = int((time.monotonic() - t0) * 1000)
        return IngestResult(
            doc_cid=doc_cid,
            chunks_indexed=len(chunks),
            was_duplicate=False,
            ms=ms,
        )

    async def ingest_pdf(
        self,
        pdf_bytes: bytes,
        *,
        title: str,
        doc_cid: str | None = None,
    ) -> IngestResult:
        t0 = time.monotonic()
        if doc_cid is None:
            doc_cid = "sha256:" + hashlib.sha256(pdf_bytes).hexdigest()
        if self._store.has_doc(doc_cid):
            return IngestResult(doc_cid=doc_cid, chunks_indexed=0, was_duplicate=True, ms=0)
        chunks = chunk_pdf(
            pdf_bytes,
            doc_metadata={"doc_cid": doc_cid, "doc_title": title},
        )
        chunks = [
            Chunk(text=c.text, metadata={**c.metadata, "chunk_index": i})
            for i, c in enumerate(chunks)
        ]
        texts = [c.text for c in chunks]
        embeddings = await self._embed_fn(texts)
        self._store.add(chunks, embeddings)
        ms = int((time.monotonic() - t0) * 1000)
        return IngestResult(
            doc_cid=doc_cid,
            chunks_indexed=len(chunks),
            was_duplicate=False,
            ms=ms,
        )
