# M24 — Reranking Service

**Spec version:** v2.0
**Depends on:** [M03 Capability Bus](../../modules/M03-capability-bus.md), [M01 Identity](../../modules/M01-identity.md), [X03 Observability](../../cross-cutting/X03-observability.md)
**Depended on by:** [M05 RAG](../../modules/M05-rag.md) (extension), [M06 Marketplace](../../modules/M06-marketplace.md) (extension)

---

## 1. Responsibility

Re-score a candidate list of documents against a query using a cross-encoder, producing a higher-precision ordering than dense retrieval alone can deliver.

The capability is intentionally narrow: take query + N short docs, return ranked list. The service does **not** retrieve documents, does **not** fetch from blobs, does **not** know about corpora. Callers (typically `rag.query` and `market.search`) do retrieval first, then ask the reranker to refine the top 100.

This is the smallest service in Phase 2 — one model, one method, no streaming — and the most underrated. Adding it to the RAG pipeline lifts answer quality more than any other Phase 2 module.

---

## 2. File layout

```
hearthnet/services/rerank/
├── __init__.py
├── service.py            # RerankService — capability registration
├── selection.py          # Picks a backend; loads on demand
└── backends/
    ├── base.py           # RerankBackend ABC
    ├── bge_reranker.py   # BGE-reranker-v2-m3 (default)
    └── cross_encoder.py  # Sentence-transformers fallback
```

---

## 3. Public API

### 3.1 `RerankBackend` (ABC)

```python
class RerankBackend(Protocol):
    name: str            # e.g. "BAAI/bge-reranker-v2-m3"
    max_doc_chars: int   # truncate longer docs

    async def score(self, query: str, documents: list[str]) -> list[float]:
        """Return one score per document, same length and order."""
        ...

    async def health(self) -> dict[str, Any]:
        """Return {"ok": bool, "loaded": bool, "model_id": ..., ...}."""
        ...
```

### 3.2 `BgeRerankerBackend`

```python
class BgeRerankerBackend:
    def __init__(self, model_id: str = "BAAI/bge-reranker-v2-m3", device: str = "auto", max_batch: int = 32):
        ...

    async def score(self, query: str, documents: list[str]) -> list[float]:
        # Tokenise (query, doc) pairs in batches of max_batch
        # Forward pass; pooled logit becomes the score
        # Higher = more relevant
        ...
```

### 3.3 `RerankService`

```python
class RerankService:
    """Bus-facing facade.  Picks backend, enforces RERANK_MAX_DOCS, emits metrics."""

    def __init__(self, bus: CapabilityBus, settings: RerankSettings, observability: Observability):
        ...

    async def start(self) -> None:
        # Register `rerank.text@1.0` on the bus
        ...

    async def rerank_text(self, body: RerankRequest) -> RerankResponse:
        # 1. Validate len(documents) <= RERANK_MAX_DOCS (else bad_request)
        # 2. Pick backend per `body.params.model` or default
        # 3. Truncate docs to backend.max_doc_chars
        # 4. Call backend.score
        # 5. Sort descending, take top_k (or all)
        # 6. Emit `rerank.latency_ms` metric
        ...
```

### 3.4 Request / response dataclasses

```python
@dataclass
class RerankDoc:
    id: str
    text: str

@dataclass
class RerankRequest:
    query:      str
    documents:  list[RerankDoc]
    top_k:      int = 10
    params:     dict[str, Any] = field(default_factory=dict)   # {"model": "..."}

@dataclass
class RerankedDoc:
    id:    str
    score: float

@dataclass
class RerankResponse:
    ranked: list[RerankedDoc]
    meta:   dict[str, Any]
```

---

## 4. Behaviour

### 4.1 Backend selection

`params.model` is matched against installed backends (key = HuggingFace model id). Default is `BAAI/bge-reranker-v2-m3` because it handles ≥100 languages including German and Latin (relevant for the OCR'd historical doc corpus).

If `params.model` is supplied but unknown → return `bad_request` with the list of installed backends.

### 4.2 Cold start

Backend is loaded lazily on first call. First call latency budget: ≤ 60s on the RTX 5090 (model ~2 GB on disk). Subsequent calls: ≤ 200ms for 50 docs at ~512 chars each.

The service publishes `model_loaded` and `model_loading` health states; `rerank.text` calls during loading wait up to `RERANK_LOAD_TIMEOUT_SECONDS` (default 60) then return `unavailable`.

### 4.3 Score semantics

Scores are **raw logits**, not normalised probabilities. They are comparable within a single call but not across calls or backends. Callers MUST NOT compare a 0.91 score from BGE to a 0.91 from cross-encoder/ms-marco — different scales.

### 4.4 Truncation

Documents longer than `backend.max_doc_chars` (default 2048) are truncated. The service logs `rerank.docs_truncated` counter. Truncation is from the right; callers who care about specific spans should pre-summarise or chunk before passing in.

### 4.5 No streaming

`rerank.text@1.0` is non-streaming. Even at 100 docs the latency is well under 1s on GPU. If a Phase-3 use case demands streaming (e.g. 1000-doc reranks for academic search), introduce `rerank.text@2.0` with `progress` frames; do not retrofit v1.

### 4.6 Integration with RAG (M05 extension)

`rag.query` in Phase 2 grows an internal pipeline:

```
1. Hybrid retrieval (dense + BM25) → top 100 candidates
2. Optional call to rerank.text@1.0 → top 10
3. Pass top 10 to llm.chat as context
```

The hop to `rerank.text` is done via the bus, not via direct import. This keeps the policy ("which model?", "is reranking available?") in the service and out of the RAG core.

If `rerank.text@1.0` is unavailable in the local mesh, RAG falls back to dense scores alone and logs `rag.rerank_skipped` counter (not an error).

### 4.7 Integration with Marketplace (M06 extension)

`market.search` follows the same pattern when the query is natural-language. For tag-based queries it skips reranking.

---

## 5. Errors

| Code | Cause |
|------|-------|
| `bad_request` | `len(documents) > RERANK_MAX_DOCS`, empty query, malformed payload |
| `unavailable` | Backend loading or hardware unavailable |
| `model_not_found` | Requested `params.model` is not installed |

`unavailable` is retryable; the other two are not.

---

## 6. Configuration

```toml
[services.rerank]
enabled                  = true
default_model            = "BAAI/bge-reranker-v2-m3"
device                   = "auto"             # "auto" | "cuda" | "cpu"
max_batch                = 32
max_doc_chars            = 2048
load_timeout_seconds     = 60
trust_required           = "member"
```

Behind a feature flag: when `enabled=false`, the capability simply does not register and RAG falls back to dense-only.

---

## 7. Tests

### 7.1 Unit
- Sorting: scores `[0.1, 0.9, 0.5]` produce ranked order `[1, 2, 0]`
- Truncation: 4000-char doc gets truncated to 2048 before scoring
- `top_k` honoured; returns at most `top_k` results
- Bad request when `documents=[]` or `len > RERANK_MAX_DOCS`

### 7.2 Integration
- End-to-end: `rag.query` with reranking vs without, on the niederrhein-emergency corpus, asserts at least one expected document moves into top 3 with rerank that wasn't there without
- Cross-language: German query, mixed German/English candidates, BGE reranker should put the German candidate first when relevance is equal

### 7.3 Performance
- 100 docs @ 1024 chars: p50 ≤ 300ms on RTX 5090; p95 ≤ 600ms
- CPU fallback (no GPU): p50 ≤ 4s for 50 docs (acceptable; degraded)

### 7.4 Failure-mode
- Backend crash mid-call: caller receives `unavailable`; service self-heals on next call
- Concurrent calls: 20 parallel reranks should not deadlock; backend serialises behind a single semaphore

---

## 8. Cross-references

- Capability spec: [CAPABILITY_CONTRACT_v2 §4.15](../CAPABILITY_CONTRACT_v2.md#415-reranktext10)
- Used by: M05 RAG extension, M06 Marketplace extension
- Observability: emits `rerank.calls_total`, `rerank.latency_ms`, `rerank.docs_truncated`, `rerank.errors_total{code}`

---

## 9. Open questions

1. **Reciprocal rank fusion** with dense scores as the alternative when rerank is unavailable — worth implementing in M05 as the fallback path?
2. **ColBERT-style late interaction** — heavier model, higher quality. Worth a second backend, or wait for Phase 3 to evaluate?
3. **Reranker for code/diff content** — different model family (e.g. `BAAI/bge-code-reranker`). Should `params.model` selection be auto-inferred from query/doc content?
4. **Caching** — query+doc-pair hash → score, evict LRU. Worth it for repeated queries in chat-driven RAG sessions, or premature optimisation?
