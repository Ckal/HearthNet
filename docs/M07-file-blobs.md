# M07 — File & Blobs

**Spec version:** v1.0
**Depends on:** M01 (identity, for signing advertise events), M03 (bus), X01 (transport, for streamed chunk transfer), X02 (events), X04 (config), `blake3`
**Depended on by:** M05 (RAG stores source PDFs as blobs), M10 (chat attachments), M08 (UI file browser)

---

## 1. Responsibility

Two coupled concerns sharing one module:

1. **Blob store** (`hearthnet.blobs.*`): on-disk content-addressed store, chunking, hash verification
2. **File service** (`hearthnet.services.file.*`): exposes `file.read`, `file.list`, `file.advertise`, `file.put` capabilities to the bus

The split exists because the blob store is also used by [M05](M05-rag.md) (for storing source PDFs) without going through the bus.

---

## 2. File layout

```
hearthnet/blobs/
├── __init__.py
├── store.py              # BlobStore: filesystem-backed CID store
├── chunker.py            # split / reassemble + BLAKE3
└── transfer.py           # parallel chunk fetch across multiple sources

hearthnet/services/file/
├── __init__.py
└── service.py            # FileService: registers file.* capabilities
```

---

## 3. Blob store (`hearthnet.blobs.*`)

### 3.1 `chunker.py`

```python
# hearthnet/blobs/chunker.py
from dataclasses import dataclass

@dataclass(frozen=True)
class ChunkRef:
    index:    int
    cid:      str          # "blake3:<hex>" of this chunk's bytes
    size_bytes: int

@dataclass(frozen=True)
class BlobManifest:
    cid:             str           # "blake3:<hex>" — the merkle root, derived from chunks
    size_bytes:      int
    chunk_size_bytes: int          # CHUNK_SIZE_BYTES = 262144
    chunks:          list[ChunkRef]
    mime_type:       str | None
    filename:        str | None    # advisory only, not part of the CID

def hash_bytes(data: bytes) -> str:
    """BLAKE3 → 'blake3:<hex>'."""

def chunk_blob(data: bytes, *, chunk_size: int = CHUNK_SIZE_BYTES) -> tuple[BlobManifest, list[bytes]]:
    """Split bytes into 256KB chunks. Compute per-chunk CID and the merkle-root CID for the manifest."""

def manifest_cid(manifest: BlobManifest) -> str:
    """Compute the manifest's CID: BLAKE3 over canonical-JSON of {chunks[].cid, size_bytes, chunk_size_bytes}."""

def reassemble(chunks: list[bytes]) -> bytes:
    """Concat chunks in index order. Caller is responsible for verifying each chunk's CID first."""

def verify_chunk(data: bytes, expected_cid: str) -> None:
    """Raises BlobError('hash_mismatch') if data's BLAKE3 != expected_cid."""
```

### 3.2 `store.py`

```python
# hearthnet/blobs/store.py
class BlobStore:
    """Sharded filesystem store at <DATA>/blobs/<aa>/<bb...>.bin"""

    def __init__(self, dir_path: Path, gc_threshold: float = BLOB_GC_DISK_THRESHOLD):
        ...

    # -- single-chunk ops --

    def has(self, cid: str) -> bool: ...
    def read_chunk(self, cid: str) -> bytes:
        """Raises BlobError('not_found') if absent. Verifies hash on read."""
    def write_chunk(self, cid: str, data: bytes) -> None:
        """Verifies hash before writing; idempotent if already present."""
    def delete_chunk(self, cid: str) -> bool: ...

    # -- blob (manifest + chunks) ops --

    def has_blob(self, manifest_cid: str) -> bool:
        """True iff the manifest exists AND all referenced chunks exist."""

    def read_manifest(self, manifest_cid: str) -> BlobManifest: ...

    def write_blob(self, manifest: BlobManifest, chunks: list[bytes]) -> None:
        """Atomically write manifest + chunks. Hash-verifies each chunk."""

    def read_blob_bytes(self, manifest_cid: str) -> bytes:
        """Reassemble whole blob into memory. For small blobs only (< 100 MB)."""

    async def read_blob_stream(self, manifest_cid: str) -> AsyncIterator[tuple[ChunkRef, bytes]]:
        """Stream chunks for large blobs."""

    # -- introspection / GC --

    def list_cids(self, prefix: str | None = None) -> list[str]: ...
    def total_bytes(self) -> int: ...
    def pin(self, cid: str) -> None: ...
    def unpin(self, cid: str) -> None: ...
    def is_pinned(self, cid: str) -> bool: ...

    def gc(self, target_fraction: float = 0.7) -> int:
        """Run LRU eviction of unpinned blobs until disk usage < target_fraction.
        Returns bytes freed."""

class BlobError(Exception):
    """code in {'not_found','hash_mismatch','io_error','disk_full','manifest_invalid'}"""
    code: str
```

### 3.3 `transfer.py`

```python
# hearthnet/blobs/transfer.py
class TransferManager:
    """Coordinates parallel chunk fetch from multiple peer sources."""

    def __init__(self, store: BlobStore, bus: CapabilityBus, concurrency: int = 4):
        ...

    async def fetch_blob(
        self,
        manifest_cid: str,
        *,
        sources: list[str] | None = None,    # NodeIDs known to hold; if None, ask via bus
    ) -> BlobManifest:
        """1. Fetch manifest (via bus.call('file.read', ...)).
        2. Determine missing chunks.
        3. For each missing chunk, pick a source (round-robin, load-aware via bus), fetch via stream.
        4. Verify each chunk, write to store.
        5. Return manifest once complete.
        Resumable: re-running after partial completion skips already-present chunks."""

    async def advertise(self, cids: list[str]) -> None:
        """Tell other nodes we hold these CIDs. Emits file.cid.advertised events
        and direct file.advertise calls to known peers (best-effort)."""
```

---

## 4. File service (`hearthnet.services.file.*`)

### 4.1 `service.py`

```python
# hearthnet/services/file/service.py
class FileService:
    name    = "file"
    version = "1.0"

    def __init__(self, config: FileConfig, store: BlobStore, event_log: EventLog):
        ...

    def capabilities(self) -> list[tuple[CapabilityDescriptor, Callable, ParamsPredicate]]:
        """Registers: file.read, file.list, file.advertise, file.put."""

    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    def health(self) -> dict: ...

    # --- handlers ---

    async def handle_read(self, req: RouteRequest) -> AsyncIterator[dict] | dict:
        """CONTRACT §4.7.
        If CID is a chunk → return single chunk JSON (non-stream).
        If CID is a manifest → stream: 'manifest' frame, then chunks, then 'done'."""

    async def handle_list(self, req: RouteRequest) -> dict:
        """CONTRACT §4.8."""

    async def handle_advertise(self, req: RouteRequest) -> dict:
        """CONTRACT §4.9.
        Records the caller as a source for the given CIDs in an in-memory index.
        Optionally emits file.cid.advertised event to gossip."""

    async def handle_put(self, req: RouteRequest) -> AsyncIterator[dict]:
        """CONTRACT §4.10.
        Client streams chunks; server verifies and stores.
        Requires trust 'trusted' (disk-poisoning risk)."""
```

### 4.2 Capability descriptors

```python
descriptor_read = CapabilityDescriptor(
    name="file.read", version=(1, 0), stability="stable",
    request_schema={...}, response_schema={...},
    stream_schema={...},    # manifest + chunk + done frames
    params={},
    max_concurrent=8,
    trust_required="member",
    timeout_seconds=300,
    idempotent=True,
)

descriptor_list = CapabilityDescriptor(
    name="file.list", version=(1, 0), stability="stable",
    request_schema={...}, response_schema={...}, stream_schema=None,
    params={}, max_concurrent=4,
    trust_required="member", timeout_seconds=5, idempotent=True,
)

descriptor_advertise = CapabilityDescriptor(
    name="file.advertise", version=(1, 0), stability="stable",
    request_schema={...}, response_schema={...}, stream_schema=None,
    params={}, max_concurrent=16,
    trust_required="member", timeout_seconds=5, idempotent=True,
)

descriptor_put = CapabilityDescriptor(
    name="file.put", version=(1, 0), stability="stable",
    request_schema={...}, response_schema={...},
    stream_schema={...},     # ready + chunk + done
    params={}, max_concurrent=2,
    trust_required="trusted", timeout_seconds=600, idempotent=True,
)
```

### 4.3 `params_compatible`

All `file.*` capabilities use the default `lambda offered, requested: True`. Any node with the capability can serve any CID it has; the bus query later checks `has(cid)` and returns `not_found` if absent.

---

## 5. Behaviour

### 5.1 Storage layout on disk

```
<DATA>/blobs/
├── ab/
│   ├── c123def456...bin         # chunk
│   └── c123def456...manifest.json
├── cd/
│   └── ...
└── pinned.txt                   # newline-separated CIDs that must not be GC'd
```

Sharded by first 2 hex chars of CID (256 directories, ~uniform).

### 5.2 Hash verification is always-on

Every read and every write verifies the chunk's BLAKE3 against its CID. Cost is small (BLAKE3 is fast); benefit is bit-rot detection and protection from a malicious advertiser sending bad bytes.

### 5.3 Pinning

- The `personal` RAG corpus pins its source documents
- Snapshot blobs are pinned by [X02](../cross-cutting/X02-events.md)
- The community manifest blob is pinned
- User-pinned via UI

Anything else is GC-eligible.

### 5.4 GC

When disk usage exceeds `BLOB_GC_DISK_THRESHOLD` (0.80), evict LRU unpinned blobs until below `0.7 × disk_capacity`. Tracked by file mtime (read updates mtime; common Linux mount option).

### 5.5 Source discovery

When a node needs a CID it doesn't have:

1. Ask the bus: `file.list@1.0` with `prefix=<short CID>` against known peers
2. Aggregate the responders into a sources list
3. Optionally also consult `file.cid.advertised` events in the log
4. Pass sources to `TransferManager.fetch_blob`

Phase 2: a DHT-like source index. MVP: per-request fan-out.

### 5.6 Concurrent fetches

`TransferManager` issues N concurrent chunk fetches across sources. Each chunk request goes via the bus (so health/quarantine work). On per-chunk failure, retry from a different source; after 3 attempts on a chunk, fail the whole blob with `partition`.

### 5.7 Backpressure on PUT

When a node receives `file.put`, it inspects free disk before accepting. If below 1 GB after putative add, refuse with `capacity_exceeded`.

---

## 6. Errors

| Condition | Wire code |
|-----------|-----------|
| CID not present | `not_found` |
| Hash verification failed | `bad_request` (caller sent corrupted bytes) |
| Out of disk | `capacity_exceeded` |
| Caller not trusted for put | `unauthorized` |
| Chunk size mismatch | `bad_request` |

---

## 7. Configuration

From [X04 §3](../cross-cutting/X04-config.md):

```python
config.file.blobs_dir       # default <DATA>/blobs
config.file.gc_threshold    # default 0.8
```

Constants: `CHUNK_SIZE_BYTES`, `BLOB_GC_DISK_THRESHOLD`.

---

## 8. Tests

### Unit
- `test_chunk_then_reassemble_roundtrip`
- `test_manifest_cid_deterministic`
- `test_verify_chunk_detects_one_bit_flip`
- `test_store_write_then_read_returns_same_bytes`
- `test_store_rejects_wrong_cid_on_write`
- `test_pinning_prevents_gc`
- `test_gc_evicts_lru_unpinned`

### Integration
- `test_two_node_blob_fetch` — node A has blob, node B requests via bus, succeeds
- `test_three_source_parallel_fetch` — three nodes hold the blob, B fetches in parallel, distribution observed
- `test_chunk_corruption_falls_over_to_alt_source` — one source returns bad chunk; fetcher retries from another
- `test_put_requires_trusted_caller`

---

## 9. Cross-references

| What | Where |
|------|-------|
| `file.*` wire | [CONTRACT §4.7–4.10](../CAPABILITY_CONTRACT.md) |
| BLAKE3 + CID format | [GLOSSARY.md](../GLOSSARY.md), [CONTRACT §1.4](../CAPABILITY_CONTRACT.md) |
| Used by RAG ingest | [M05 §3.3](M05-rag.md) |
| Used by chat attachments | [M10 §3.3](M10-chat.md) |
| `file.cid.advertised` event | [CONTRACT §7.2](../CAPABILITY_CONTRACT.md), [X02](../cross-cutting/X02-events.md) |
| Snapshot pinning | [X02 §5](../cross-cutting/X02-events.md) |

---

## 10. Open questions

1. **DHT source index** — Phase 2 nice-to-have.
2. **Background replication** — Phase 2: a node may auto-replicate blobs of high "interest" (referenced by recent events). Out of scope MVP.
3. **Encrypted blobs** — for personal corpus, blobs are stored in cleartext on local disk. Add at-rest encryption Phase 2.
4. **Resumable PUT mid-transfer crash** — Phase 1.5: server keeps a partial-transfer index keyed by client_id + manifest_cid; client can resume.
