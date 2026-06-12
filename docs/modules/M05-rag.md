# M05 — RAG Service

**Spec version:** v1.0
**Depends on:** M03 (bus, for both registration and invoking embed.text), M07 (blobs, for source document storage), X04 (config), X03 (observability), X02 (events, for `rag.document.ingested`), `chromadb`, `pypdf`
**Depended on by:** M08 (UI), other applications that consume retrieved chunks

---

## 1. Responsibility

Implement `rag.query@1.0`, `rag.ingest@1.0`, `rag.list_corpora@1.0`. Maintain per-corpus vector stores. Chunk and embed ingested documents. Store original document blobs via [M07](M07-file-blobs.md).

RAG is **never** the LLM provider — answer generation is a separate hop the caller makes after retrieving chunks. This separation is deliberate: it keeps `rag.query` cacheable and reusable.

---

## 2. File layout

```
hearthnet/services/rag/
├── __init__.py
├── service.py          # RagService
├── chunker.py          # text → chunks
├── ingest.py           # document → chunks → embeddings → store
└── store.py            # ChromaDB wrapper, one collection per corpus
```

---

## 3. Public API

### 3.1 `chunker.py`

```python
# hearthnet/services/rag/chunker.py
@dataclass(frozen=True)
class Chunk:
    text:     str
    metadata: dict      # {doc_cid, doc_title, page, chunk_index, language}

def chunk_text(
    text: str,
    *,
    tokens_per_chunk: int = RAG_CHUNK_TOKENS,        # 1000
    overlap_tokens:   int = RAG_CHUNK_OVERLAP_TOKENS, # 200
    metadata: dict | None = None,
) -> list[Chunk]:
    """Split using a sliding window measured in approximate tokens.
    Respects paragraph boundaries where possible; falls back to sentence then word."""

def chunk_pdf(pdf_bytes: bytes, *, doc_metadata: dict) -> list[Chunk]:
    """Extract text per page using pypdf, then chunk_text per page.
    Each chunk carries page number in metadata."""
```

### 3.2 `store.py`

```python
# hearthnet/services/rag/store.py
class CorpusStore:
    """One ChromaDB collection per corpus name."""

    def __init__(self, corpora_dir: Path, corpus: str, embedding_dim: int):
        ...

    def add_chunks(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None: ...
    def has_document(self, doc_cid: str) -> bool: ...
    def query(
        self,
        embedding: list[float],
        *,
        k: int,
        filter: dict | None = None,
    ) -> list[ScoredChunk]: ...
    def count(self) -> int: ...
    def size_bytes(self) -> int: ...
    def language_majority(self) -> str | None: ...

@dataclass(frozen=True)
class ScoredChunk:
    chunk:    Chunk
    score:    float    # similarity, higher = better

def list_corpora(corpora_dir: Path) -> list[str]: ...
def corpus_info(corpora_dir: Path, corpus: str) -> dict: ...
```

### 3.3 `ingest.py`

```python
# hearthnet/services/rag/ingest.py
class IngestPipeline:
    def __init__(
        self,
        bus: CapabilityBus,           # to call embed.text@1.0
        blob_store: BlobStore,        # from M07
        corpora_dir: Path,
        event_log: EventLog,
    ):
        ...

    async def ingest_document(
        self,
        doc_cid: str,
        corpus: str,
        title: str,
        language: str,
        metadata: dict,
        author_kp: KeyPair,
    ) -> IngestResult:
        """1. Fetch blob bytes from blob_store by doc_cid (assumed already stored).
        2. Detect content type (currently: PDF only).
        3. Chunk.
        4. Batch embed via bus.call('embed.text', (1,0), ...).
        5. Write to CorpusStore.
        6. Append rag.document.ingested event via event_log.
        Idempotent on doc_cid: re-ingesting is a no-op (logged, returns existing result)."""

@dataclass(frozen=True)
class IngestResult:
    doc_cid:        str
    chunks_indexed: int
    tokens_indexed: int
    ingest_event_id: str
    ms:             int
```

### 3.4 `service.py`

```python
# hearthnet/services/rag/service.py
class RagService:
    name    = "rag"
    version = "1.0"

    def __init__(
        self,
        config: RagConfig,
        bus: CapabilityBus,
        blob_store: BlobStore,
        event_log: EventLog,
        community_manifest_provider: Callable[[], CommunityManifest],
    ):
        self._stores: dict[str, CorpusStore] = {}
        self._ingest = IngestPipeline(bus, blob_store, config.corpora_dir, event_log)

    def capabilities(self) -> list[tuple[CapabilityDescriptor, Callable, ParamsPredicate]]:
        """Registers one entry per existing corpus for rag.query (params include corpus name).
        rag.ingest registered once (corpus is a request param).
        rag.list_corpora registered once."""

    async def start(self) -> None:
        """Discover existing corpora on disk, open ChromaDB collections."""

    async def stop(self) -> None: ...
    def health(self) -> dict: ...

    # --- handlers ---

    async def handle_query(self, req: RouteRequest) -> dict:
        """CONTRACT §4.4.
        1. Embed query via bus.call('embed.text', (1,0), ...).
        2. CorpusStore.query(embedding, k).
        3. Format response."""

    async def handle_ingest(self, req: RouteRequest) -> dict:
        """CONTRACT §4.5.
        Checks caller is at least 'trusted'.
        Delegates to IngestPipeline.ingest_document."""

    async def handle_list_corpora(self, req: RouteRequest) -> dict:
        """CONTRACT §4.6."""
```

### 3.5 Capability descriptors and predicates

```python
# rag.query: registered per corpus
descriptor_query = CapabilityDescriptor(
    name="rag.query", version=(1, 0), stability="stable",
    request_schema={...}, response_schema={...}, stream_schema=None,
    params={"corpus": "<corpus_name>", "embedding_model": "<model>", "k_max": RAG_MAX_K},
    max_concurrent=4,
    trust_required="member",
    timeout_seconds=10,
    idempotent=True,
)

def query_params_compatible(offered: dict, requested: dict) -> bool:
    return requested.get("corpus") == offered.get("corpus")

# rag.ingest: registered once
descriptor_ingest = CapabilityDescriptor(
    name="rag.ingest", version=(1, 0), stability="stable",
    request_schema={...}, response_schema={...}, stream_schema=None,
    params={"corpora_available": "<list of corpus names>"},
    max_concurrent=2,
    trust_required="trusted",
    timeout_seconds=300,
    idempotent=True,
)
```

---

## 4. Behaviour

### 4.1 Embedding via the bus, not direct import

`RagService` never imports `EmbeddingService`. It uses `bus.call("embed.text", (1, 0), ...)`. Reasons:
- Embeddings might run on another node (e.g. a GPU anchor) while RAG runs on a CPU hearth
- The bus handles load balancing and quarantine automatically
- Keeps the service module dependency graph honest

### 4.2 Corpus naming

- `[a-z0-9-]+` only, max 64 chars
- One corpus per ChromaDB collection
- Two reserved names: `personal` (per-user, NEVER federated) and `system` (read-only, ships with HearthNet)

### 4.3 Ingest idempotency

A `(corpus, doc_cid)` already in the store is a no-op. This makes re-ingestion safe across restarts and gossip re-delivery of `rag.document.ingested` events.

### 4.4 Event log integration

After a successful ingest, append a `rag.document.ingested` event ([X02 §3.1](../cross-cutting/X02-events.md), [CONTRACT §7.2](../CAPABILITY_CONTRACT.md)). Other nodes seeing this event MAY pre-fetch the blob (via `file.read`) and ingest into their own RAG corpus, depending on their replication policy. (Replication policy is out of scope for MVP; nodes do not auto-replicate.)

### 4.5 Multi-tenant isolation

Each corpus is open in read or read/write mode by the node. The `personal` corpus is local-only and is NEVER routable from other nodes (the service does not register a `rag.query` capability for it).

### 4.6 PDF extraction quality

`pypdf` is OK for digital PDFs. For scanned PDFs, OCR is needed; this is M-Phase-2 (`ocr.*` namespace). Ingest of a scanned PDF without OCR will produce empty chunks; service detects and returns `bad_request` with hint.

### 4.7 Query language detection

Optional: detect query language; pass as metadata filter to the store. MVP: detection skipped; caller's filter is respected.

---

## 5. Composition flow (typical user query)

```
UI → bus.call("llm.chat", ..., body containing user message)
         ↓ (handler in LLM service, but UI may also explicitly call rag.query first)
UI → bus.call("rag.query", (1,0), {params: {corpus: ...}, input: {query: ...}})
         ↓
RagService.handle_query
   → bus.call("embed.text", (1,0), ...)       # may go remote
   → CorpusStore.query → list[ScoredChunk]
   → return chunks with metadata
         ↓
UI builds prompt with chunks + question
UI → bus.call("llm.chat", ..., messages including context)
```

The UI orchestrates this in M08. RAG service does NOT chain into the LLM itself.

---

## 6. Errors

| Condition | Wire code |
|-----------|-----------|
| Unknown corpus on query | `not_found` |
| `k > RAG_MAX_K` | `bad_request` |
| Blob not resolvable on ingest | `not_found` |
| Unsupported MIME type on ingest | `bad_request` |
| Caller not trusted for ingest | `unauthorized` |
| Embedding model unavailable (no embed.text providers) | `partition` (bus quarantine state) |

---

## 7. Configuration

From [X04 §3](../cross-cutting/X04-config.md):

```python
config.rag.enabled       # bool
config.rag.corpora_dir   # default <CACHE>/embeddings
```

Constants: `RAG_CHUNK_TOKENS`, `RAG_CHUNK_OVERLAP_TOKENS`, `RAG_DEFAULT_K`, `RAG_MAX_K`.

---

## 8. Tests

### Unit
- `test_chunk_text_respects_paragraph_boundaries`
- `test_chunk_pdf_carries_page_number`
- `test_corpus_store_add_then_query_recovers_chunk`
- `test_ingest_idempotent_on_doc_cid`
- `test_query_handler_calls_embed_via_bus_not_direct_import`
- `test_query_handler_rejects_unknown_corpus`
- `test_personal_corpus_not_registered_as_capability`

### Integration
- `test_demo_corpus_query_returns_relevant_chunks` — load the 6 demo PDFs, query, expect top hit
- `test_ingest_then_other_node_sees_event` — two-node gossip
- `test_query_falls_back_to_remote_when_local_corpus_missing` — two nodes, only one has corpus

---

## 9. Cross-references

| What | Where |
|------|-------|
| `rag.*` wire spec | [CONTRACT §4.4–4.6](../CAPABILITY_CONTRACT.md) |
| Service protocol | [M03 §4](M03-bus.md) |
| Uses embed.text | [M11](M11-embedding.md) |
| Uses blob store | [M07 §3](M07-file-blobs.md) |
| Emits rag.document.ingested | [X02](../cross-cutting/X02-events.md), [CONTRACT §7.2](../CAPABILITY_CONTRACT.md) |
| UI query composition | [M08 §4](M08-ui.md) |

---

## 10. Open questions

1. **Re-embedding when models change** — if the configured embedding model changes, the existing corpora are stale. Decision (MVP): refuse to start with mismatched model; print a `hearthnet rag reindex` hint. Phase 2: auto-reindex.
2. **Federation of corpora** — Phase 2: a corpus may be marked "federated" and queries fan out to other communities. Out of scope here.
3. **Reranking** — Phase 2: a `rerank.text@1.0` capability could be inserted between embedding and final ranking. Reserved namespace.
4. **Hybrid search** — keyword + dense. ChromaDB has limited support. Phase 2.
