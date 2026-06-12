"""M05 Federated RAG — multi-node scatter-gather query with reranking.

Strategy mix:
  A — single-best routing (handled by plain rag.query)
  B — scatter-gather: fan out to all peers, merge results
  C — local-first: return immediately when local confidence is high
  E — MoE routing: use moe.route to prioritise which peers to query first

Capability: rag.federated_query v1.0

Spec: docs/M05-rag.md §9 (distributed query path)
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from hearthnet.bus.capability import CapabilityDescriptor, RouteRequest

_log = logging.getLogger(__name__)

_DEFAULT_CONFIDENCE = 0.5  # local-first threshold (C)
_DEFAULT_FANOUT_TIMEOUT = 4.0  # seconds per remote call (B)
_DEFAULT_K = 5


class FederatedRagService:
    """Registers rag.federated_query on the capability bus.

    Constructor args:
        bus             — CapabilityBus (required; used for scatter-gather calls)
        corpus          — corpus name filter; None = any corpus
        confidence_threshold — local score threshold for early return (C strategy)
        fanout_timeout  — per-peer timeout in seconds (B strategy)
    """

    name = "rag.federated"
    version = "1.0"

    def __init__(
        self,
        bus: Any,
        *,
        corpus: str | None = None,
        confidence_threshold: float = _DEFAULT_CONFIDENCE,
        fanout_timeout: float = _DEFAULT_FANOUT_TIMEOUT,
    ) -> None:
        self._bus = bus
        self._corpus = corpus
        self._confidence = confidence_threshold
        self._fanout_timeout = fanout_timeout

    def capabilities(self) -> list[tuple]:
        params: dict[str, Any] = {}
        if self._corpus:
            params["corpus"] = self._corpus
        return [
            (
                CapabilityDescriptor(
                    name="rag.federated_query",
                    version=(1, 0),
                    params=params,
                    max_concurrent=4,
                    idempotent=True,
                ),
                self.handle_federated_query,
                self._corpus_matches,
            ),
        ]

    def _corpus_matches(self, offered: dict, requested: dict) -> bool:
        return (
            not requested.get("corpus")
            or not offered.get("corpus")
            or requested.get("corpus") == offered.get("corpus")
        )

    # ------------------------------------------------------------------
    # Main handler
    # ------------------------------------------------------------------

    async def handle_federated_query(self, req: RouteRequest) -> dict[str, Any]:
        """Federated query: local-first → scatter-gather → merge → rerank."""
        inp = req.body.get("input", {})
        query: str = inp.get("query", "")
        k: int = int(inp.get("k", _DEFAULT_K))
        corpus: str | None = inp.get("corpus", self._corpus)
        threshold: float = float(inp.get("confidence_threshold", self._confidence))

        if not query:
            return {"output": {"chunks": []}, "meta": {"corpus": corpus, "federated": False}}

        # ── Strategy C: local-first ────────────────────────────────────────
        local_chunks, local_node_id, best_local_score = await self._query_local(query, k, corpus)

        if best_local_score >= threshold and local_chunks:
            _log.debug("federated_query: local-first short-circuit score=%.3f", best_local_score)
            _add_source(local_chunks, local_node_id)
            return {
                "output": {"chunks": local_chunks[:k]},
                "meta": {
                    "corpus": corpus,
                    "federated": False,
                    "peers_asked": 0,
                    "reranked": False,
                },
            }

        # ── Strategy E: MoE — prioritise peers by topic ────────────────────
        peer_priority: list[str] | None = await self._moe_peer_priority(query, corpus)

        # ── Strategy B: scatter-gather ─────────────────────────────────────
        query_body = {
            "input": {"query": query, "k": k * 2, "corpus": corpus},
            "params": {"corpus": corpus} if corpus else {},
        }
        all_results = await self._bus.call_all(
            "rag.query",
            (1, 0),
            query_body,
            include_local=False,  # we already queried local above
            timeout_seconds=self._fanout_timeout,
            max_providers=6,
        )
        peers_asked = len(all_results)

        # Reorder by MoE priority if we got one
        if peer_priority:

            def _priority_key(item: tuple[str, dict]) -> int:
                try:
                    return peer_priority.index(item[0])
                except ValueError:
                    return len(peer_priority)

            all_results.sort(key=_priority_key)

        # ── Merge local + remote ───────────────────────────────────────────
        merged: list[dict[str, Any]] = []
        _add_source(local_chunks, local_node_id)
        merged.extend(local_chunks)

        for node_id, result in all_results:
            chunks = result.get("output", {}).get("chunks", [])
            _add_source(chunks, node_id)
            merged.extend(chunks)

        # ── Deduplicate by doc_cid / text fingerprint ─────────────────────
        merged = _dedupe(merged)

        # ── Rerank via M24 rerank.text ────────────────────────────────────
        reranked = False
        if len(merged) > k:
            try:
                rerank_body = {
                    "input": {
                        "query": query,
                        "docs": [{"id": str(i), "text": c["text"]} for i, c in enumerate(merged)],
                        "top_k": k,
                    }
                }
                rerank_result = await self._bus.call("rerank.text", (1, 0), rerank_body)
                ranked = rerank_result.get("output", {}).get("ranked", [])
                if ranked:
                    idx_score = {int(r["id"]): r["score"] for r in ranked}
                    for i, chunk in enumerate(merged):
                        chunk["score"] = idx_score.get(i, chunk.get("score", 0.0))
                    merged.sort(key=lambda c: c.get("score", 0.0), reverse=True)
                    reranked = True
            except Exception as exc:
                _log.debug("rerank.text unavailable, falling back to score sort: %s", exc)
                merged.sort(key=lambda c: c.get("score", 0.0), reverse=True)

        # Re-number ranks
        for i, chunk in enumerate(merged[:k]):
            chunk["rank"] = i + 1

        return {
            "output": {"chunks": merged[:k]},
            "meta": {
                "corpus": corpus,
                "federated": True,
                "peers_asked": peers_asked,
                "reranked": reranked,
            },
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _query_local(
        self, query: str, k: int, corpus: str | None
    ) -> tuple[list[dict], str, float]:
        """Query the local rag.query and return (chunks, node_id, best_score)."""
        body: dict[str, Any] = {
            "input": {"query": query, "k": k, "corpus": corpus},
            "params": {"corpus": corpus} if corpus else {},
        }
        try:
            result = await self._bus.call("rag.query", (1, 0), body)
            chunks = result.get("output", {}).get("chunks", [])
            best = max((c.get("score", 0.0) for c in chunks), default=0.0)
            return chunks, self._bus.node_id_full, best
        except Exception as exc:
            _log.debug("local rag.query failed: %s", exc)
            return [], self._bus.node_id_full, 0.0

    async def _moe_peer_priority(self, query: str, corpus: str | None) -> list[str] | None:
        """Ask moe.route to rank which expert peers to prefer. Returns node_ids or None."""
        tags = [corpus] if corpus else []
        try:
            result = await self._bus.call(
                "moe.route",
                (1, 0),
                {"input": {"query": query, "top_k": 4, "tags": tags}},
            )
            candidates = result.get("output", {}).get("candidates", [])
            return [c["expert_id"] for c in candidates if "expert_id" in c]
        except Exception:
            return None


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _add_source(chunks: list[dict], node_id: str) -> None:
    """Attach source_node provenance to each chunk in-place."""
    for chunk in chunks:
        chunk.setdefault("source_node", node_id)


def _dedupe(chunks: list[dict]) -> list[dict]:
    """Remove duplicate chunks (same doc_cid or same text fingerprint)."""
    seen: set[str] = set()
    out: list[dict] = []
    for chunk in chunks:
        meta = chunk.get("metadata") or {}
        doc_cid = meta.get("doc_cid") or meta.get("source")
        if doc_cid:
            key = doc_cid
        else:
            text = chunk.get("text", "")
            key = hashlib.sha256(text.encode()).hexdigest()
        if key not in seen:
            seen.add(key)
            out.append(chunk)
    return out
