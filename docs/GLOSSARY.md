# HearthNet Glossary

Canonical names. Every spec uses these. Do not introduce synonyms.

---

## Identifiers

| Term | Form | Notes |
|------|------|-------|
| **NodeID** | `ed25519:XXXX-XXXX-XXXX-XXXX` | First 8 bytes of Ed25519 public key, base32, grouped by 4 |
| **NodeID (full)** | `ed25519:<base64-url-nopad>` of full pubkey | Used only in manifests; never displayed to users |
| **CommunityID** | `ed25519:<...>` of community root pubkey | Same format as full NodeID |
| **CapabilityName** | dotted lowercase: `llm.chat`, `rag.query` | Namespace allocation: see CONTRACT §3.1 |
| **Version** | `(major, minor)` tuple — wire form `"1.0"` | Patch component does not exist on the wire |
| **SchemaHash** | `blake3:<hex>` | BLAKE3 of canonical-JSON of capability schema |
| **CID** | `blake3:<hex>` | Content identifier for blobs |
| **EventID** | ULID (26 chars, monotonic, encodes wall-clock) | Globally unique per community in practice |
| **TraceID** | ULID | Identifies one logical request across hops |
| **Signature** | `ed25519:<base64-url-nopad>` | Always over canonical-JSON |
| **WallClock** | RFC 3339 UTC: `2026-05-26T08:14:22Z` | Display-only; never used for ordering |
| **Lamport** | `int >= 0` | Per-community monotonic logical counter |
| **Topic** | dotted lowercase: `marketplace.post.created` | Pub-sub topic name |

---

## Concepts

| Term | Definition |
|------|------------|
| **Anchor** | A node profile: always-on, GPU-equipped, primary capability provider |
| **Hearth** | A node profile: mid-tier, typically a laptop, runs some services |
| **Spark** | A node profile: thin client (Pi, mobile, browser); consumes capabilities |
| **Bridge** | A node profile: relay-only, no inference, federates communities (Phase 2) |
| **Profile** | One of `anchor` / `hearth` / `spark` / `bridge` — declared in node manifest |
| **Community** | A trust root: a group of nodes sharing one root key and one event log |
| **Federation** | Cross-community trust + capability access (Phase 2) |
| **Capability** | A named, versioned, schema-bound RPC offered by a node |
| **Capability descriptor** | The metadata for one capability: name, version, schema, params, guarantees |
| **Capability entry** | The bus's local record of one remote capability: descriptor + health |
| **Bus / capability bus** | The L3 routing component each service registers with |
| **Service** | An L4 module that provides one or more capabilities |
| **Node manifest** | A signed JSON document describing what a node is and offers; expires every 30s |
| **Community manifest** | A signed JSON document describing community membership and policy |
| **Event** | A signed, Lamport-stamped record in the community's append-only log |
| **Event log** | The community's full ordered history; one SQLite db per node |
| **Snapshot** | A signed materialised state at some Lamport |
| **Materialised view** | A derived index built by replaying events (member list, marketplace, etc.) |
| **Blob** | An immutable byte string identified by its CID |
| **Chunk** | A 256KB slice of a blob, itself CID-addressed |
| **TrustLevel** | One of `unknown` / `member` / `trusted` / `anchor` |
| **Stability** | One of `experimental` / `beta` / `stable` for a capability |
| **Emergency mode** | UI + behavioural state when the internet-detector reports offline |

---

## Errors (closed set — see CONTRACT §9)

| Code | Meaning |
|------|---------|
| `not_found` | No node offers the requested capability, or the requested resource is gone |
| `capacity_exceeded` | Node is at declared `max_concurrent`; retry with backoff or pick another |
| `schema_mismatch` | Request body does not match the declared schema for this capability/version |
| `unauthorized` | Caller is not a community member, or lacks the required trust level |
| `revoked` | Caller's NodeID is in the revoked set of the community |
| `internal_error` | Service crashed handling this request |
| `not_implemented` | Capability is declared but the handler is a stub |
| `timeout` | Operation exceeded its declared deadline |
| `partition` | Remote node is presumed unreachable (mDNS lost, repeated failures) |
| `invalid_signature` | Signature verification failed on a manifest, event, or request |
| `expired` | Manifest, token, or event TTL has passed |
| `rate_limited` | Caller exceeded the per-peer-per-capability rate budget |
| `bad_request` | Malformed JSON, missing required field, etc. |

---

## File paths (XDG-style; resolved via `platformdirs`)

| Path | Purpose |
|------|---------|
| `<DATA>/keys/device.ed25519` | Private key, 0600 |
| `<DATA>/keys/device.pub` | Public key |
| `<DATA>/communities/<community_id>/manifest.json` | Latest signed community manifest |
| `<DATA>/communities/<community_id>/events.sqlite` | Event log |
| `<DATA>/communities/<community_id>/snapshots/<lamport>.bin` | Signed snapshots |
| `<DATA>/blobs/<aa>/<bb...>` | CID-addressed blobs |
| `<CONFIG>/config.toml` | User configuration |
| `<CACHE>/embeddings/<corpus>` | Vector store on-disk files |
| `<LOG>/<date>.log` | Daily rotating logs |

`<DATA>` = `platformdirs.user_data_dir("hearthnet")` (Linux: `~/.local/share/hearthnet/`).

---

## Default ports

| Port | Purpose | Configurable? |
|------|---------|---------------|
| 7080 | Bus HTTP server | yes (`config.transport.port`) |
| 7860 | Gradio UI | yes (`config.ui.port`) |
| 42424 | UDP discovery multicast | no (interop) |
| 5353 | mDNS | no (system) |

---

## Defaults (numeric — central reference)

| Constant | Value | Where defined |
|----------|-------|---------------|
| `MANIFEST_TTL_SECONDS` | 30 | M01 |
| `MANIFEST_REPUBLISH_INTERVAL_SECONDS` | 20 | M01 |
| `DISCOVERY_UDP_INTERVAL_SECONDS` | 5 (active) / 30 (stable) | M02 |
| `EMERGENCY_PROBE_INTERVAL_SECONDS` | 10 (online) / 2 (offline) | M09 |
| `EMERGENCY_PROBE_TIMEOUT_SECONDS` | 2 | M09 |
| `EMERGENCY_TRANSITION_DEBOUNCE_SECONDS` | 30 | M09 |
| `CONNECTION_IDLE_SECONDS` | 60 | X01 |
| `RECONNECT_BACKOFF_CAP_SECONDS` | 30 | X01 |
| `STREAM_WINDOW_FRAMES` | 16 | X01 |
| `STREAM_ACK_INTERVAL_FRAMES` | 8 | X01 |
| `STREAM_ACK_TIMEOUT_SECONDS` | 5 | X01 |
| `RPC_DEFAULT_TIMEOUT_SECONDS` | 30 | X01 |
| `LLM_GENERATION_DEFAULT_TIMEOUT_SECONDS` | 120 | M04 |
| `CHUNK_SIZE_BYTES` | 262144 (256 KiB) | M07 |
| `BLOB_GC_DISK_THRESHOLD` | 0.80 | M07 |
| `RAG_CHUNK_TOKENS` | 1000 | M05 |
| `RAG_CHUNK_OVERLAP_TOKENS` | 200 | M05 |
| `RAG_DEFAULT_K` | 5 | M05 |
| `RAG_MAX_K` | 20 | M05 |
| `HEALTH_WINDOW_CALLS` | 100 | M03 |
| `HEALTH_QUARANTINE_THRESHOLD` | 0.5 | M03 |
| `HEALTH_QUARANTINE_SECONDS` | 60 | M03 |
| `RATE_LIMIT_SOFT_RPS_PER_CAP` | 10 | X01 |
| `RATE_LIMIT_HARD_RPS_PER_CAP` | 100 | X01 |
| `RATE_LIMIT_SOFT_RPS_TOTAL` | 100 | X01 |
| `RATE_LIMIT_HARD_RPS_TOTAL` | 1000 | X01 |
| `EVENT_LOG_RETENTION_DAYS` | 30 | X02 |
| `SNAPSHOT_LAG_LAMPORT` | 1000 | X02 |
| `TRACE_RING_BUFFER` | 10000 | X03 |
| `LOG_RETENTION_DAYS` | 14 | X03 |

Implementation hint: put these in `hearthnet/constants.py` and import everywhere. Do not hardcode in modules.
