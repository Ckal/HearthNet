from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path

from hearthnet.services.rag.chunker import Chunk

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScoredChunk:
    chunk: Chunk
    score: float  # higher = better


class CorpusStore:
    """Persistent vector store — chromadb if available, SQLite otherwise.

    Backend selection (in order of preference):
      1. chromadb PersistentClient  — if chromadb is installed
      2. SQLite (one .db file per corpus) — always available, survives restart
      3. in-memory list              — last resort if SQLite also fails

    The active backend is logged at WARNING level so it is visible in Space logs.
    ``self._dir.mkdir()`` runs unconditionally so the corpora directory always
    exists regardless of which backend wins.
    """

    def __init__(self, corpora_dir: Path, corpus_name: str) -> None:
        self._dir = corpora_dir
        self._corpus = corpus_name
        self._use_chroma = False
        self._chroma_client = None
        self._collection = None
        self._db: sqlite3.Connection | None = None
        # Pure in-memory fallback (only used when SQLite init also fails)
        self._items: list[tuple[Chunk, list[float]]] = []

        # Always create the directory — independent of which backend is chosen.
        self._dir.mkdir(parents=True, exist_ok=True)

        self._try_init_chroma()
        if not self._use_chroma:
            self._init_sqlite()

        if self._use_chroma:
            backend = "chroma"
        elif self._db is not None:
            backend = "sqlite"
        else:
            backend = "in-memory/ephemeral"
        _log.warning("RAG vector store: using %s backend for corpus '%s'", backend, corpus_name)

    # ------------------------------------------------------------------
    # Backend initialisation
    # ------------------------------------------------------------------

    def _try_init_chroma(self) -> None:
        try:
            import chromadb  # type: ignore[import-untyped]

            self._chroma_client = chromadb.PersistentClient(path=str(self._dir / self._corpus))
            self._collection = self._chroma_client.get_or_create_collection(self._corpus)
            self._use_chroma = True
        except ImportError:
            pass

    def _init_sqlite(self) -> None:
        db_path = self._dir / f"{self._corpus}.db"
        try:
            self._db = sqlite3.connect(str(db_path), check_same_thread=False)
            self._db.execute("""
                CREATE TABLE IF NOT EXISTS chunks (
                    id TEXT PRIMARY KEY,
                    doc_cid TEXT,
                    chunk_text TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    embedding_json TEXT NOT NULL
                )
            """)
            self._db.execute("CREATE INDEX IF NOT EXISTS idx_doc_cid ON chunks(doc_cid)")
            self._db.commit()
        except Exception as exc:
            _log.warning("RAG SQLite init failed, using in-memory fallback: %s", exc)
            self._db = None

    # ------------------------------------------------------------------
    # Write path
    # ------------------------------------------------------------------

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
        elif self._db is not None:
            rows = [
                (
                    str(uuid.uuid4()),
                    chunk.metadata.get("doc_cid"),
                    chunk.text,
                    json.dumps(dict(chunk.metadata)),
                    json.dumps(emb),
                )
                for chunk, emb in zip(chunks, embeddings, strict=False)
            ]
            self._db.executemany(
                "INSERT INTO chunks(id, doc_cid, chunk_text, metadata_json, embedding_json)"
                " VALUES (?,?,?,?,?)",
                rows,
            )
            self._db.commit()
        else:
            for chunk, emb in zip(chunks, embeddings, strict=False):
                self._items.append((chunk, emb))

    # ------------------------------------------------------------------
    # Read path
    # ------------------------------------------------------------------

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
            # chromadb distances are L2; convert to similarity score
            distances = results.get("distances", [[]])[0]
            for doc, meta, dist in zip(docs, metas, distances, strict=False):
                score = 1.0 / (1.0 + dist)
                scored.append(ScoredChunk(chunk=Chunk(text=doc, metadata=meta), score=score))
            return scored

        # SQLite: load all rows, cosine-rank in Python
        if self._db is not None:
            rows = self._db.execute(
                "SELECT chunk_text, metadata_json, embedding_json FROM chunks"
            ).fetchall()
            if not rows:
                return []
            scored_items: list[tuple[Chunk, float]] = []
            for chunk_text, meta_json, emb_json in rows:
                try:
                    meta = json.loads(meta_json)
                    emb = json.loads(emb_json)
                    score = self._cosine_similarity(embedding, emb)
                    scored_items.append((Chunk(text=chunk_text, metadata=meta), score))
                except Exception:
                    continue
            scored_items.sort(key=lambda x: x[1], reverse=True)
            return [ScoredChunk(chunk=c, score=s) for c, s in scored_items[:k]]

        # Pure in-memory fallback
        if not self._items:
            return []
        mem_scored = [
            (chunk, self._cosine_similarity(embedding, emb)) for chunk, emb in self._items
        ]
        mem_scored.sort(key=lambda x: x[1], reverse=True)
        return [ScoredChunk(chunk=chunk, score=score) for chunk, score in mem_scored[:k]]

    def has_doc(self, doc_cid: str) -> bool:
        """True if any chunk with this doc_cid exists."""
        if self._use_chroma and self._collection is not None:
            results = self._collection.get(where={"doc_cid": doc_cid}, limit=1, include=[])
            return len(results.get("ids", [])) > 0
        if self._db is not None:
            row = self._db.execute(
                "SELECT 1 FROM chunks WHERE doc_cid = ? LIMIT 1", (doc_cid,)
            ).fetchone()
            return row is not None
        return any(c.metadata.get("doc_cid") == doc_cid for c, _ in self._items)

    def count(self) -> int:
        if self._use_chroma and self._collection is not None:
            return self._collection.count()
        if self._db is not None:
            row = self._db.execute("SELECT COUNT(*) FROM chunks").fetchone()
            return row[0] if row else 0
        return len(self._items)

    def clear(self) -> None:
        if self._use_chroma and self._collection is not None and self._chroma_client is not None:
            self._chroma_client.delete_collection(self._corpus)
            self._collection = self._chroma_client.get_or_create_collection(self._corpus)
        elif self._db is not None:
            self._db.execute("DELETE FROM chunks")
            self._db.commit()
        else:
            self._items.clear()

    def corpus_info(self) -> dict:
        """Return backend metadata — exposed via Settings tab and node manifest."""
        if self._use_chroma:
            backend = "chroma"
            persistent = True
        elif self._db is not None:
            backend = "sqlite"
            persistent = True
        else:
            backend = "in-memory"
            persistent = False
        return {
            "backend": backend,
            "persistent": persistent,
            "chunks": self.count(),
            "corpus": self._corpus,
        }

    def _cosine_similarity(self, a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b, strict=False))
        na = sum(x**2 for x in a) ** 0.5
        nb = sum(x**2 for x in b) ** 0.5
        return dot / (na * nb) if na and nb else 0.0


def list_corpora(corpora_dir: Path) -> list[str]:
    """List corpus names found under corpora_dir."""
    if not corpora_dir.exists():
        return []
    return sorted(p.name for p in corpora_dir.iterdir() if p.is_dir() or p.suffix == ".db")


def corpus_info(corpora_dir: Path, corpus: str) -> dict:
    """Return {corpus, exists, count_chunks, backend, persistent}."""
    corpus_dir = corpora_dir / corpus
    db_path = corpora_dir / f"{corpus}.db"
    exists = corpus_dir.exists() or db_path.exists()
    if exists:
        store = CorpusStore(corpora_dir, corpus)
        return store.corpus_info()
    return {"corpus": corpus, "exists": False, "count_chunks": 0, "backend": "none", "persistent": False}
