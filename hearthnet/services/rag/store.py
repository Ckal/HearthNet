from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from hearthnet.services.rag.chunker import Chunk


@dataclass(frozen=True)
class ScoredChunk:
    chunk: Chunk
    score: float  # higher = better


class CorpusStore:
    """In-memory vector store with cosine similarity.

    Uses chromadb if available, else falls back to in-memory list.
    """

    def __init__(self, corpora_dir: Path, corpus_name: str) -> None:
        self._dir = corpora_dir
        self._corpus = corpus_name
        self._use_chroma = False
        self._chroma_client = None
        self._collection = None
        # Fallback: in-memory list of (chunk, embedding)
        self._items: list[tuple[Chunk, list[float]]] = []
        self._try_init_chroma()

    def _try_init_chroma(self) -> None:
        try:
            import chromadb  # type: ignore[import-untyped]

            self._dir.mkdir(parents=True, exist_ok=True)
            self._chroma_client = chromadb.PersistentClient(path=str(self._dir / self._corpus))
            self._collection = self._chroma_client.get_or_create_collection(self._corpus)
            self._use_chroma = True
        except ImportError:
            pass

    def add(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        """Add chunks with their embeddings."""
        if self._use_chroma and self._collection is not None:
            ids = [str(uuid.uuid4()) for _ in chunks]
            documents = [c.text for c in chunks]
            metadatas = [dict(c.metadata) for c in chunks]
            self._collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas,
            )
        else:
            for chunk, emb in zip(chunks, embeddings, strict=False):
                self._items.append((chunk, emb))

    def query(self, embedding: list[float], k: int = 5) -> list[ScoredChunk]:
        """Return top-k chunks by cosine similarity."""
        if self._use_chroma and self._collection is not None:
            n = min(k, self._collection.count())
            if n == 0:
                return []
            results = self._collection.query(
                query_embeddings=[embedding],
                n_results=n,
                include=["documents", "metadatas", "distances"],
            )
            scored: list[ScoredChunk] = []
            docs = results.get("documents", [[]])[0]
            metas = results.get("metadatas", [[]])[0]
            # chromadb distances are L2 by default; convert to similarity
            distances = results.get("distances", [[]])[0]
            for doc, meta, dist in zip(docs, metas, distances, strict=False):
                score = 1.0 / (1.0 + dist)
                scored.append(ScoredChunk(chunk=Chunk(text=doc, metadata=meta), score=score))
            return scored
        if not self._items:
            return []
        scored_items = [
            (chunk, self._cosine_similarity(embedding, emb)) for chunk, emb in self._items
        ]
        scored_items.sort(key=lambda x: x[1], reverse=True)
        return [ScoredChunk(chunk=chunk, score=score) for chunk, score in scored_items[:k]]

    def has_doc(self, doc_cid: str) -> bool:
        """True if any chunk with this doc_cid exists."""
        if self._use_chroma and self._collection is not None:
            results = self._collection.get(where={"doc_cid": doc_cid}, limit=1, include=[])
            return len(results.get("ids", [])) > 0
        return any(c.metadata.get("doc_cid") == doc_cid for c, _ in self._items)

    def count(self) -> int:
        if self._use_chroma and self._collection is not None:
            return self._collection.count()
        return len(self._items)

    def clear(self) -> None:
        if self._use_chroma and self._collection is not None and self._chroma_client is not None:
            self._chroma_client.delete_collection(self._corpus)
            self._collection = self._chroma_client.get_or_create_collection(self._corpus)
        else:
            self._items.clear()

    def _cosine_similarity(self, a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b, strict=False))
        na = sum(x**2 for x in a) ** 0.5
        nb = sum(x**2 for x in b) ** 0.5
        return dot / (na * nb) if na and nb else 0.0


def list_corpora(corpora_dir: Path) -> list[str]:
    """List corpus names found under corpora_dir."""
    if not corpora_dir.exists():
        return []
    return sorted(p.name for p in corpora_dir.iterdir() if p.is_dir())


def corpus_info(corpora_dir: Path, corpus: str) -> dict:
    """Return {corpus, exists, count_chunks}."""
    corpus_path = corpora_dir / corpus
    exists = corpus_path.exists()
    count = 0
    if exists:
        store = CorpusStore(corpora_dir, corpus)
        count = store.count()
    return {"corpus": corpus, "exists": exists, "count_chunks": count}
