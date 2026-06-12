# HearthNet Capability Contract

**Spec version:** v1.0
**Last touched:** 2026-06-07
**Scope:** wire-level protocol, capability schemas, event schemas, signing rules.

This document is the source of truth. Any conflict with a module spec is resolved in favour of this document.

---

## 1. Conventions

### 1.1 Encodings

- **Wire format**: JSON, UTF-8, no BOM. Numbers fit IEEE 754 double; integers fit in 53 bits. Where 64-bit precision is needed (rare), use strings.
- **Binary content**: Base64-URL without padding, prefixed by encoding tag where ambiguous (`ed25519:`, `blake3:`).
- **Timestamps**: RFC 3339 UTC with `Z`, e.g. `2026-05-26T08:14:22Z`. No timezone offsets, no fractional seconds beyond milliseconds (`...22.281Z` is allowed for tracing only).
- **Durations**: integer seconds, suffix `_seconds` in field names.
- **Sizes**: integer bytes, suffix `_bytes`. UI may convert to KB/MB; wire never does.

### 1.2 Canonical JSON

For any payload that is signed or hashed, the canonical form is:

- Keys sorted lexicographically at every level
- No whitespace between tokens
- Numbers without trailing zeros: `1.0` → `1`, `1.10` → `1.1`
- Strings UTF-8, non-ASCII characters not escaped
- `null` allowed only where the schema declares it

A reference implementation is `hearthnet.identity.keys.canonical_json(obj) -> bytes`. Use it always.

### 1.3 Signing primitive

Ed25519 over the canonical-JSON byte string of the payload excluding the `signature` field itself. The signature field is added back after signing. To verify, strip `signature`, re-canonicalise, verify.

### 1.4 Hashing primitive

BLAKE3. Output: 32 bytes, presented as lowercase hex with the prefix `blake3:`. Where short forms are needed (display), use the first 16 hex chars: `blake3:abc123...`. The full hex is always used in protocol fields.

### 1.5 Identifier forms

See [GLOSSARY.md](GLOSSARY.md). Identifiers in protocol payloads always use the full form. Display forms are UI-only.

---

## 2. Versioning

### 2.1 Capability version

A capability declares `version: "X.Y"` where X is major, Y is minor.

- **Compatibility**: a request asking for `name@>=A.B` is satisfied by an offered `name@X.Y` iff `X == A` and `Y >= B`.
- **Major bumps**: breaking. Old callers receive `schema_mismatch`.
- **Minor bumps**: additive only. Old callers continue to work. New fields are optional with documented defaults.
- The `schema_hash` (BLAKE3 of the request + response schema) is recomputed on every bump. Two nodes with the same `schema_hash` for a capability speak identically.

### 2.2 Contract version

This document is versioned independently of capabilities. Node manifests carry `contract_version: "1.0"` so peers can refuse to talk to incompatible contract revisions.

### 2.3 Event schema version

Each event carries a `schema_version` field. Old events are kept verbatim; readers translate via a versioned schema registry. Never rewrite history.

---

## 3. Capability namespace

### 3.1 Prefix allocation

| Prefix | Owner | Stability of prefix | Defined in |
|--------|-------|---------------------|------------|
| `llm.*` | LLM service | stable | M04 |
| `embed.*` | Embedding service | stable | M11 |
| `rag.*` | RAG service | stable | M05 |
| `file.*` | File service | stable | M07 |
| `market.*` | Marketplace | stable | M06 |
| `chat.*` | Chat | stable | M10 |
| `community.*` | Trust ops | stable | M01 + X02 |
| `federation.*` | Cross-community | beta | Phase 2 |
| `ocr.*` | OCR (Phase 2) | reserved | — |
| `tts.*` `stt.*` | Speech (Phase 2) | reserved | — |
| `trans.*` | Translation (Phase 2) | reserved | — |
| `img.*` | Images (Phase 2) | reserved | — |
| `experimental.*` | Anything not promoted | unstable | any |

Reserved prefixes may not be used. Capabilities outside the reserved set must start with `experimental.`.

### 3.2 Complete capability list (this release)

| Name | Stability | Stream? | Trust required | Section |
|------|-----------|---------|----------------|---------|
| `llm.chat@1.0` | stable | yes | member | §4.1 |
| `llm.complete@1.0` | stable | yes | member | §4.2 |
| `embed.text@1.0` | stable | no | member | §4.3 |
| `rag.query@1.0` | stable | no | member | §4.4 |
| `rag.ingest@1.0` | stable | no | trusted | §4.5 |
| `rag.list_corpora@1.0` | stable | no | member | §4.6 |
| `file.read@1.0` | stable | yes (chunks) | member | §4.7 |
| `file.list@1.0` | stable | no | member | §4.8 |
| `file.advertise@1.0` | stable | no | member | §4.9 |
| `file.put@1.0` | stable | yes (chunks) | trusted | §4.10 |
| `market.list@1.0` | stable | no | member | §4.11 |
| `market.post@1.0` | stable | no | member | §4.12 |
| `market.expire@1.0` | stable | no | member (own only) | §4.13 |
| `market.search@1.0` | stable | no | member | §4.14 |
| `chat.send@1.0` | stable | no | member | §4.15 |
| `chat.history@1.0` | stable | no | member (self only) | §4.16 |
| `community.invite@1.0` | stable | no | member with invite right | §4.17 |
| `community.revoke@1.0` | stable | no | 3 of trusted | §4.18 |

`federation.*`, `ocr.*`, `tts.*`, `stt.*`, `trans.*`, `img.*` are out of scope for this release; placeholders only.

---

## 4. Per-capability specifications

For each capability the spec gives:

- **Purpose**
- **Trust required**
- **Idempotency**
- **Request schema** (JSON Schema-ish; required fields marked)
- **Response schema** (or stream frame schema)
- **Errors** (codes that this capability may return beyond the universal set)
- **Example request and response**

The universal error codes apply to every capability: `bad_request`, `unauthorized`, `revoked`, `capacity_exceeded`, `internal_error`, `timeout`, `partition`, `invalid_signature`, `expired`, `rate_limited`.

### 4.1 `llm.chat@1.0`

- **Purpose**: Multi-turn chat completion. Server-streams tokens.
- **Trust**: member
- **Idempotency**: no (token sampling is non-deterministic)
- **Stream**: yes (SSE)
- **Multi-model providers**: a node serving several models (e.g. a local backend
  plus an opt-in sponsor backend) registers a single `llm.chat@1.0` whose
  descriptor advertises the primary model in `params.model` and the full catalogue
  in `params.models` (array). The bus matches a requested `model` against this
  catalogue and dispatches to the owning backend.

#### Request

```json
{
  "params": {
    "model": "qwen2.5-7b-instruct",          // required, must match an offered model
    "ctx": 8192                              // optional, default = declared max
  },
  "input": {
    "messages": [                            // required, ≥ 1
      {"role": "system", "content": "..."},  // optional
      {"role": "user",   "content": "..."},  // required at least once
      {"role": "assistant", "content": "..."}
    ],
    "max_tokens":   512,                     // optional, default 1024
    "temperature":  0.7,                     // optional, default 0.7
    "top_p":        0.95,                    // optional, default 0.95
    "stop":         ["</s>"],                // optional
    "seed":         42,                      // optional; if set, server SHOULD make deterministic
    "tools":        [],                      // optional, OpenAI-compatible tool defs (Phase 2)
    "tool_choice":  "auto",                  // optional
    "stream":       true                     // optional, default true
  }
}
```

#### Response — non-stream (only if `stream:false`)

```json
{
  "output": {
    "message": {"role": "assistant", "content": "..."},
    "tool_calls": []                         // optional
  },
  "meta": {
    "model": "qwen2.5-7b-instruct",
    "tokens_in": 42,
    "tokens_out": 178,
    "stop_reason": "end",                    // "end" | "max_tokens" | "stop_sequence" | "cancelled"
    "ms": 1834
  }
}
```

#### Stream frames

```
event: token
data: {"text":"Sie ", "logprob": -0.21}

event: tool_call_delta                       (only if tools used; Phase 2)
data: {"id":"...","name":"search","arguments_delta":"{\"q\":\"..."}

event: done
data: {"tokens_out": 178, "stop_reason": "end", "ms": 1834}
```

A `done` frame is always sent. Client closing the connection mid-stream cancels generation within 200ms (server SHOULD abort).

#### Errors

Beyond universal:
- `not_implemented` — server registered the capability but backend is missing the model
- `bad_request` — malformed messages, empty messages, role sequence violation

### 4.2 `llm.complete@1.0`

- **Purpose**: Single-shot completion (no chat structure). Used by RAG internally and by classical tooling.
- **Trust**: member
- **Stream**: yes

#### Request

```json
{
  "params": {"model": "qwen2.5-7b-instruct"},
  "input": {
    "prompt":       "...",                   // required
    "max_tokens":   256,
    "temperature":  0.7,
    "top_p":        0.95,
    "stop":         ["\n\n"],
    "seed":         null,
    "stream":       true
  }
}
```

#### Response (non-stream)

```json
{
  "output": {"text": "..."},
  "meta": {"model": "...", "tokens_in": 12, "tokens_out": 80, "stop_reason": "end", "ms": 312}
}
```

#### Stream frames

Same as `llm.chat` but only `token` and `done`. No `tool_call_delta`.

### 4.3 `embed.text@1.0`

- **Purpose**: Embed one or many strings into vectors.
- **Trust**: member
- **Idempotency**: yes (assuming deterministic backend)

#### Request

```json
{
  "params": {"model": "bge-small-en-v1.5"},
  "input":  {
    "texts": ["...", "...", "..."],          // required, 1..256
    "normalize": true                        // optional, default true
  }
}
```

#### Response

```json
{
  "output": {
    "embeddings": [[0.012, -0.043, ...], [...], [...]],
    "dim": 384
  },
  "meta": {"model": "bge-small-en-v1.5", "ms": 38}
}
```

#### Errors

- `bad_request` — > 256 texts, or any text > 8192 chars

### 4.4 `rag.query@1.0`

- **Purpose**: Retrieve top-K relevant chunks from a named corpus.
- **Trust**: member
- **Idempotency**: yes

#### Request

```json
{
  "params": {"corpus": "niederrhein-emergency"},
  "input": {
    "query":  "Wie reinige ich Regenwasser?",
    "k":      5,                             // optional, default 5, max 20
    "filter": {                              // optional metadata filter
      "language": "de",
      "min_year": 2000
    },
    "include_text": true                     // optional, default true
  }
}
```

#### Response

```json
{
  "output": {
    "chunks": [
      {
        "rank": 1,
        "score": 0.84,
        "text":  "Regenwasser kann durch Filtration ...",
        "metadata": {
          "doc_cid": "blake3:...",
          "doc_title": "Notfall-Trinkwasser",
          "page": 12,
          "chunk_id": "ch_001"
        }
      }
    ]
  },
  "meta": {"corpus": "niederrhein-emergency", "ms": 24, "embedding_model": "bge-small-en-v1.5"}
}
```

#### Errors

- `not_found` — corpus does not exist
- `bad_request` — k > 20

### 4.5 `rag.ingest@1.0`

- **Purpose**: Add a document to a corpus.
- **Trust**: trusted (corpus pollution is a real risk)
- **Idempotency**: by content hash (`doc_cid`)

#### Request

```json
{
  "params": {"corpus": "niederrhein-emergency"},
  "input": {
    "doc_cid": "blake3:...",                 // required; document must already be in blob store
    "title":   "Notfall-Trinkwasser",
    "language": "de",
    "metadata": {"author": "...", "year": 2024}
  }
}
```

#### Response

```json
{
  "output": {
    "doc_cid": "blake3:...",
    "chunks_indexed": 87,
    "tokens_indexed": 18342
  },
  "meta": {"corpus": "niederrhein-emergency", "ms": 4210, "ingest_event_id": "01HXR..."}
}
```

The ingest also publishes a `rag.document.ingested` event (§7).

#### Errors

- `not_found` — `doc_cid` not resolvable to a blob
- `bad_request` — unsupported media type

### 4.6 `rag.list_corpora@1.0`

#### Request

```json
{"params": {}, "input": {}}
```

#### Response

```json
{
  "output": {
    "corpora": [
      {"name": "niederrhein-emergency", "docs": 6, "chunks": 412, "size_bytes": 18243842, "language_majority": "de"}
    ]
  },
  "meta": {"ms": 2}
}
```

### 4.7 `file.read@1.0`

- **Purpose**: Fetch a single chunk by CID, or a whole blob via streaming chunks.
- **Trust**: member
- **Stream**: yes (chunk frames)

#### Request

```json
{
  "params": {},
  "input":  {"cid": "blake3:..."}            // either a chunk CID or a blob manifest CID
}
```

#### Response (single chunk, non-stream)

If `cid` resolves to a chunk:

```json
{
  "output": {
    "cid": "blake3:...",
    "size_bytes": 262144,
    "data_b64": "..."                        // chunk bytes, base64
  },
  "meta": {"ms": 5}
}
```

#### Stream frames (manifest CID, multi-chunk)

If `cid` resolves to a blob manifest:

```
event: manifest
data: {"cid":"blake3:...","size_bytes":4824711,"chunk_size_bytes":262144,"chunks":[{"i":0,"cid":"blake3:..."}, ...]}

event: chunk
data: {"i":0,"cid":"blake3:...","size_bytes":262144,"data_b64":"..."}

event: chunk
data: {"i":1,"cid":"blake3:...","size_bytes":262144,"data_b64":"..."}

event: done
data: {"chunks":19,"ms":4218}
```

Clients verify each chunk's BLAKE3 before storing.

#### Errors

- `not_found` — server does not have this CID

### 4.8 `file.list@1.0`

#### Request

```json
{"params": {}, "input": {"prefix": "blake3:abc"}}    // prefix optional
```

#### Response

```json
{"output": {"cids": ["blake3:abc...", "blake3:abd..."]}, "meta": {"ms": 3}}
```

### 4.9 `file.advertise@1.0`

- **Purpose**: Used during gossip sync; one node tells another it now holds a CID.
- **Trust**: member
- **Idempotency**: yes

#### Request

```json
{"params": {}, "input": {"cids": ["blake3:..."]}}
```

#### Response

```json
{"output": {"recorded": 1}, "meta": {"ms": 1}}
```

### 4.10 `file.put@1.0`

- **Purpose**: Offer a blob to a remote node (typically used to share an emergency PDF widely).
- **Trust**: trusted
- **Stream**: yes (client-stream of chunks)

#### Request — initial frame

```json
{"params": {}, "input": {"manifest": {"cid":"blake3:...", "size_bytes":..., "chunks":[...]}}}
```

Server responds with a `ready` event including a list of chunks it does not yet have. Client then streams those chunks. On completion, server replies with `done`.

```
event: ready
data: {"needed":[0,1,2,3, ...]}

(client sends:)
event: chunk
data: {"i":0,"cid":"blake3:...","data_b64":"..."}

(server:)
event: done
data: {"received":4,"ms":1832}
```

#### Errors

- `unauthorized` — caller not trusted
- `capacity_exceeded` — disk full or GC threshold reached

### 4.11 `market.list@1.0`

- **Purpose**: List current (non-expired) marketplace posts in this community.
- **Trust**: member
- **Idempotency**: yes (snapshot read)

#### Request

```json
{
  "params": {},
  "input": {
    "category": "offer",                     // optional: "offer" | "request" | "info" | "emergency"
    "tags":     ["wasser"],                  // optional
    "since_lamport": 4000,                   // optional, for delta sync
    "limit":    50                           // optional, default 50, max 500
  }
}
```

#### Response

```json
{
  "output": {
    "posts": [
      {
        "event_id": "01HXR...",
        "lamport":  4218,
        "author":   "ed25519:...",
        "category": "request",
        "title":    "Suche Wasserkanister, 20L",
        "body":     "...",
        "location": {"lat": 51.5, "lng": 6.2, "label": "Issum"},
        "tags":     ["wasser","notfall"],
        "created_at": "2026-05-26T08:14:22Z",
        "expires_at": "2026-05-27T08:14:22Z"
      }
    ],
    "max_lamport": 4231
  },
  "meta": {"ms": 8}
}
```

### 4.12 `market.post@1.0`

- **Purpose**: Create a marketplace post.
- **Trust**: member
- **Idempotency**: yes, by `client_id` (caller-generated UUID)

#### Request

```json
{
  "params": {},
  "input": {
    "client_id": "01HXR...",                 // required, used for dedup
    "category":  "request",
    "title":     "Suche Wasserkanister, 20L",
    "body":      "Brauche bis morgen ...",
    "location":  {"lat": 51.5, "lng": 6.2, "label": "Issum"},
    "tags":      ["wasser","notfall"],
    "ttl_seconds": 86400                     // optional, default 7 days, max 30 days
  }
}
```

#### Response

```json
{
  "output": {"event_id": "01HXR...", "lamport": 4218},
  "meta": {"ms": 6}
}
```

The post emits a `market.post.created` event (§7).

### 4.13 `market.expire@1.0`

#### Request

```json
{
  "params": {},
  "input": {
    "client_id": "01HXR...",                 // dedup
    "event_id":  "01HXR...",                 // the original post's id
    "reason":    "fulfilled"                 // "fulfilled" | "withdrawn" | "user_request" | "stale"
  }
}
```

#### Response

```json
{"output": {"event_id": "01HXS...", "lamport": 4252}, "meta": {"ms": 3}}
```

#### Errors

- `unauthorized` — caller is not the original author and not a trusted moderator
- `not_found` — original post not found

### 4.14 `market.search@1.0`

- **Purpose**: Semantic search across posts using embeddings.
- **Trust**: member

#### Request

```json
{
  "params": {},
  "input": {
    "query": "wasser notfall kanister",
    "k": 10
  }
}
```

#### Response

Same shape as `market.list` but ordered by semantic similarity. Each post has an additional `score` field.

### 4.15 `chat.send@1.0`

- **Purpose**: Send a direct message to one recipient.
- **Trust**: member
- **Idempotency**: yes, by `client_id`

#### Request

```json
{
  "params": {},
  "input": {
    "client_id":  "01HXR...",
    "recipient":  "ed25519:...",             // recipient NodeID (full form)
    "body":       "Hi, hast du heute Strom?",
    "attachments": [                         // optional
      {"cid": "blake3:...", "name": "schaltplan.pdf"}
    ]
  }
}
```

#### Response

```json
{"output": {"event_id": "01HXR...", "lamport": 4301, "delivered": "direct"}, "meta": {"ms": 4}}
```

`delivered` is `"direct"` if recipient is online, `"forwarded"` if held by store-and-forward, `"queued"` if no anchor is willing.

### 4.16 `chat.history@1.0`

- **Purpose**: Retrieve local chat history with one peer.
- **Trust**: self only — node returns only its own conversations
- **Idempotency**: yes

#### Request

```json
{
  "params": {},
  "input": {
    "peer":  "ed25519:...",                  // optional; if omitted, return all peers
    "since_lamport": 4000,
    "limit": 200
  }
}
```

#### Response

```json
{
  "output": {
    "messages": [
      {
        "event_id": "01HXR...",
        "lamport":  4301,
        "from":     "ed25519:...",
        "to":       "ed25519:...",
        "body":     "...",
        "attachments": [],
        "created_at": "2026-05-26T08:14:22Z",
        "delivered_at": "2026-05-26T08:14:23Z",
        "read_at":      "2026-05-26T08:15:00Z"
      }
    ]
  },
  "meta": {"ms": 5}
}
```

### 4.17 `community.invite@1.0`

- **Purpose**: Invite a new device into the community.
- **Trust**: member with the `can_invite` policy bit
- **Idempotency**: yes, by `invitee_node_id`

#### Request

```json
{
  "params": {},
  "input": {
    "invitee_node_id": "ed25519:...",        // full pubkey
    "display_name":    "Hannes' Tablet",
    "initial_level":   "member",             // "member" or "trusted"
    "expires_at":      "2026-05-27T00:00:00Z"
  }
}
```

#### Response

```json
{
  "output": {
    "invite_blob": "ed25519:<base64-url-nopad>"   // a signed, scannable invite, encoded for QR
  },
  "meta": {"event_id": "01HXR...", "lamport": 4310, "ms": 3}
}
```

The invite produces a `community.member.invited` event. The invitee redeems it locally; redemption creates a `community.member.joined` event.

### 4.18 `community.revoke@1.0`

- **Purpose**: Remove a member. Requires 3 trusted-member signatures over the same revocation payload.
- **Trust**: see signature requirements

#### Request

```json
{
  "params": {},
  "input": {
    "client_id": "01HXR...",
    "target_node_id": "ed25519:...",
    "reason": "compromised|inactive|policy_violation|other",
    "co_signers": [
      {"node_id": "ed25519:...", "signature": "ed25519:..."},
      {"node_id": "ed25519:...", "signature": "ed25519:..."},
      {"node_id": "ed25519:...", "signature": "ed25519:..."}
    ]
  }
}
```

The co-signatures are each over the canonical-JSON of the payload excluding `co_signers` (i.e. each co-signer signs the revoke intent independently). The caller is one of the co-signers; the bus rejects with `unauthorized` if fewer than 3 distinct trusted signers are present.

#### Response

```json
{"output": {"event_id": "01HXR...", "lamport": 4400}, "meta": {"ms": 7}}
```

---

## 5. Wire format

### 5.1 Request

```http
POST /bus/v1/call HTTP/1.1
Host: <host>:<port>
Content-Type: application/json
Accept: application/json, text/event-stream
X-HearthNet-Capability: <capability_name>
X-HearthNet-Capability-Version: <major.minor>
X-HearthNet-Request-Id: <trace_id_ulid>
X-HearthNet-From: <full_node_id>
X-HearthNet-Community: <full_community_id>
X-HearthNet-Timestamp: <wall_clock>
X-HearthNet-Signature: <ed25519_signature>

<JSON body>
```

The signature covers the canonical JSON of:

```json
{
  "capability": "...",
  "version": "1.0",
  "request_id": "...",
  "from": "...",
  "community": "...",
  "timestamp": "...",
  "body": <request body, canonicalised>
}
```

Servers verify by reconstructing this object and checking the signature against the caller's pubkey (derived from `X-HearthNet-From`).

### 5.2 Response — non-stream

```http
HTTP/1.1 200 OK
Content-Type: application/json
X-HearthNet-Request-Id: <trace_id>
X-HearthNet-From: <server_node_id>
X-HearthNet-Timestamp: <wall_clock>
X-HearthNet-Signature: <ed25519 over response>

<JSON body>
```

Servers SHOULD sign responses. Clients MAY ignore the signature for non-mutating capabilities. For all `*.post`, `*.invite`, `*.revoke`, `*.ingest`, `*.expire`, `chat.send`, signature verification is mandatory.

### 5.3 Response — stream

```http
HTTP/1.1 200 OK
Content-Type: text/event-stream
X-HearthNet-Request-Id: <trace_id>
X-HearthNet-From: <server_node_id>

event: <event_name>
data: <JSON, single line>

event: <event_name>
data: <JSON>
...
```

Frame events:

- `token`, `tool_call_delta`, `chunk`, `manifest`, `ready` — capability-specific
- `progress` — `data: {"current": N, "total": M, "stage": "..."}` (any capability)
- `ack` — `data: {"upto": N}` (client → server backpressure)
- `error` — terminal error frame, replaces `done`
- `done` — terminal success frame

Every stream ends with exactly one of `done` or `error`. After that the connection closes.

### 5.4 Error response

```http
HTTP/1.1 <status>
Content-Type: application/json
X-HearthNet-Request-Id: <trace_id>

{
  "error":   "<code>",
  "message": "<human-readable, optional>",
  "retry_after_ms": 2000,
  "alt_capabilities": ["llm.chat@0.9"],
  "alt_nodes": ["ed25519:..."],
  "schema_hash_expected": "blake3:..."        // only for schema_mismatch
}
```

### 5.5 Status code mapping

| Status | Error codes |
|--------|-------------|
| 200 | (success) |
| 400 | `bad_request`, `schema_mismatch` |
| 401 | `invalid_signature`, `unauthorized` |
| 403 | `revoked` |
| 404 | `not_found` |
| 408 | `timeout` |
| 410 | `expired` |
| 429 | `rate_limited`, `capacity_exceeded` |
| 500 | `internal_error` |
| 501 | `not_implemented` |
| 503 | `partition` |

For streams, an `error` frame replaces these; the HTTP status is 200 because the stream was accepted.

---

## 6. Manifests

### 6.1 Node manifest

```json
{
  "version": 1,
  "contract_version": "1.0",
  "node_id": "ed25519:<full_pubkey>",
  "display_name": "garage-pc",
  "community_id": "ed25519:<full_pubkey>",
  "profile": "anchor",
  "endpoints": [
    {"transport": "https", "host": "192.168.188.25", "port": 7080}
  ],
  "hardware": {
    "gpu":           "RTX 5090",
    "vram_gb":       32,
    "ram_gb":        128,
    "cpu_cores":     24,
    "disk_free_gb":  4000
  },
  "capabilities": [
    {
      "name":         "llm.chat",
      "version":      "1.0",
      "stability":    "stable",
      "schema_hash":  "blake3:...",
      "params":       {"model": "qwen2.5-7b-instruct", "quant": "q4_k_m", "ctx": 8192},
      "max_concurrent": 4
    }
  ],
  "uptime_seconds": 43210,
  "load": {"cpu": 0.12, "vram_used_gb": 6.4, "in_flight_total": 0},
  "issued_at":  "2026-05-26T08:14:22Z",
  "expires_at": "2026-05-26T08:14:52Z",
  "signature":  "ed25519:..."
}
```

#### Rules

- `expires_at - issued_at == 30 s` exactly
- Re-issued every `MANIFEST_REPUBLISH_INTERVAL_SECONDS` (20s)
- Signed by the node's device key
- Stale manifests (past `expires_at`) are rejected with `expired`
- Verifying nodes pin the first-seen public key per `node_id`; a later manifest with a different key for the same `node_id` is rejected with `invalid_signature`

### 6.2 Community manifest

```json
{
  "version": 1,
  "community_id": "ed25519:<root_pubkey>",
  "name": "Niederrhein Demo",
  "root_key": "ed25519:<root_pubkey>",
  "created_at": "2026-05-26T08:00:00Z",
  "lamport_at_creation": 0,
  "policy": {
    "min_signatures_to_invite": 1,
    "min_signatures_to_demote": 3,
    "min_signatures_to_revoke": 3,
    "capability_token_ttl_seconds": 86400,
    "federation_enabled": true,
    "default_member_can_invite": true
  },
  "members": [
    {
      "node_id":   "ed25519:...",
      "level":     "anchor",
      "added_at":  "2026-05-26T08:00:00Z",
      "added_by":  "ed25519:..."
    }
  ],
  "revoked": [
    {"node_id": "ed25519:...", "revoked_at": "..."}
  ],
  "head_lamport": 4218,
  "signature": "ed25519:..."
}
```

The community manifest is **derived** from the event log. It is the materialised view at `head_lamport`. It is signed by either the root key (initial creation) or any anchor (subsequent regeneration). Other nodes verify regenerations by replaying events from the previous head.

---

## 7. Events (the community log)

### 7.1 Common event envelope

```json
{
  "schema_version": 1,
  "event_id":       "01HXR...",              // ULID
  "lamport":        4218,
  "wall_clock":     "2026-05-26T08:14:22Z",
  "community_id":   "ed25519:...",
  "author":         "ed25519:...",
  "event_type":     "market.post.created",
  "data":           { /* type-specific */ },
  "signature":      "ed25519:..."            // over canonical JSON of all above
}
```

### 7.2 Canonical event types

For each: `data` schema, who may produce, who consumes.

#### `community.created`

```json
{
  "name": "Niederrhein Demo",
  "founder_node_id": "ed25519:...",
  "policy": { /* full policy as in community manifest */ }
}
```

Producer: founder, exactly once at community birth.
Consumer: all.

#### `community.member.invited`

```json
{
  "invitee_node_id": "ed25519:...",
  "display_name":    "Hannes' Tablet",
  "initial_level":   "member",
  "expires_at":      "2026-05-27T00:00:00Z"
}
```

Producer: any member with `can_invite`.
Consumer: all.

#### `community.member.joined`

```json
{
  "invite_event_id": "01HXR...",
  "node_manifest":   { /* full manifest at join time */ }
}
```

Producer: the invitee, on first connection.
Consumer: all.

#### `community.member.revoked`

```json
{
  "target_node_id": "ed25519:...",
  "reason":         "compromised",
  "co_signers":     [{"node_id":"...", "signature":"..."}, ...]
}
```

Producer: any trusted member who has gathered 3 co-signatures.
Consumer: all.

#### `community.member.promoted` / `community.member.demoted`

```json
{
  "target_node_id": "ed25519:...",
  "new_level":      "trusted",
  "co_signers":     [...]
}
```

Producer: trusted member with required signatures (1 promote, 3 demote).
Consumer: all.

#### `community.policy.updated`

```json
{
  "policy": { /* new policy */ }
}
```

Producer: root key only.
Consumer: all.

#### `node.manifest.updated`

```json
{
  "manifest": { /* full node manifest */ }
}
```

Producer: each node, advisory; not strictly required in the log but useful for replay-based audit.
Consumer: all.

#### `market.post.created`

```json
{
  "client_id": "...",
  "category": "request",
  "title":    "...",
  "body":     "...",
  "location": {"lat":..., "lng":..., "label":"..."},
  "tags":     ["..."],
  "ttl_seconds": 86400
}
```

Producer: any member.
Consumer: all.

#### `market.post.updated`

```json
{
  "client_id": "...",
  "target_event_id": "01HXR...",
  "fields": {"body": "..."}
}
```

Producer: original author only.
Consumer: all.

#### `market.post.expired`

```json
{
  "client_id": "...",
  "target_event_id": "01HXR...",
  "reason": "fulfilled|withdrawn|user_request|stale"
}
```

Producer: original author OR any trusted moderator (with `reason != "user_request"`).
Consumer: all.

#### `chat.message.sent`

```json
{
  "client_id": "...",
  "recipient": "ed25519:...",
  "body":      "...",
  "attachments": [{"cid":"...","name":"..."}]
}
```

Producer: sender.
Consumer: sender + recipient (others may see envelope only, but `data` MAY be encrypted in Phase 2).

#### `chat.message.delivered`

```json
{"target_event_id": "01HXR...", "delivered_at": "..."}
```

Producer: recipient.
Consumer: sender.

#### `chat.message.read`

```json
{"target_event_id": "01HXR...", "read_at": "..."}
```

Producer: recipient (optional, may be disabled by user).
Consumer: sender.

#### `file.cid.advertised`

```json
{"cid": "blake3:...", "sizes_bytes": 4824711}
```

Producer: holder.
Consumer: all (used for fan-out file discovery).

#### `file.cid.unpinned`

```json
{"cid": "blake3:..."}
```

Producer: holder.
Consumer: all.

#### `rag.document.ingested`

```json
{
  "corpus":   "niederrhein-emergency",
  "doc_cid":  "blake3:...",
  "title":    "...",
  "language": "de",
  "chunks":   87
}
```

Producer: ingester.
Consumer: all members.

#### `federation.peer.added` / `federation.peer.removed` (Phase 2)

Reserved.

### 7.3 Lamport rules

Every node maintains a per-community Lamport counter.

```
on send:    lamport_send = ++lamport
on receive: lamport = max(lamport, received.lamport) + 1
```

### 7.4 Ordering

- Replay order: by `lamport` ascending, tie-broken by `event_id` ascending (ULIDs sort by time naturally)
- Conflict resolution: last-writer-wins by Lamport; `community.member.revoked` is checked first when replaying actions by the revoked party

### 7.5 Snapshots

A snapshot at Lamport L is:

```json
{
  "schema_version": 1,
  "community_id": "ed25519:...",
  "lamport": <L>,
  "wall_clock": "...",
  "state": { /* materialised views: community manifest, marketplace_current, ... */ },
  "covers_events_up_to": <L>,
  "signature": "ed25519:..."
}
```

Signed by any anchor. Other nodes verify the signature and the membership of the signer.

### 7.6 Sync protocol (gossip)

Two nodes meeting:

1. A → B: `GET /sync/v1/heads` → returns `{community_id: max_lamport}` per known community
2. A computes delta; for each community where A is ahead, A → B: `POST /sync/v1/events` with all events `lamport > B.head`
3. B verifies signatures, applies, returns `{accepted, rejected, new_head_lamport}`
4. Roles reverse; B sends what A is missing

This is also covered in [X02 §6](cross-cutting/X02-events.md).

---

## 8. Pub-sub topics

Topics are used for live notifications between connected peers (in addition to durable events in the log).

| Topic | Payload | Producer | Subscriber |
|-------|---------|----------|------------|
| `community.member.added` | event envelope | any member | all |
| `community.member.revoked` | event envelope | trusted | all |
| `node.manifest.updated` | manifest | each node | all |
| `marketplace.post.created` | event envelope | any member | all |
| `marketplace.post.expired` | event envelope | author or trusted | all |
| `chat.message.<recipient>` | event envelope | sender | recipient |
| `emergency.mode.changed` | `{online: bool, since: "..."}` | each node locally | local UI only — never on the wire |
| `federation.peer.added` | event envelope | anchor | all anchors |
| `capability.registered` | descriptor | local bus | local UI only |
| `capability.deregistered` | name+version | local bus | local UI only |

Transport: HTTP long-polling for MVP (`GET /pubsub/v1/subscribe?topic=...`), WebSocket in Phase 2.

---

## 9. Error codes (complete reference)

| Code | When | Retry? |
|------|------|--------|
| `bad_request` | Malformed payload | no, fix and resend |
| `schema_mismatch` | Schema hash differs | no, upgrade and resend |
| `invalid_signature` | Signature verification failed | no |
| `unauthorized` | Caller lacks required trust level | no |
| `revoked` | Caller's NodeID is revoked | no |
| `expired` | Manifest or token past `expires_at` | no, re-issue and resend |
| `not_found` | Resource doesn't exist | no |
| `not_implemented` | Capability declared but unimplemented | no |
| `timeout` | Exceeded server-side deadline | yes, with backoff |
| `partition` | Peer unreachable | yes, with backoff |
| `capacity_exceeded` | Concurrent limit reached | yes, honour `retry_after_ms` |
| `rate_limited` | Rate budget exceeded | yes, honour `retry_after_ms` |
| `internal_error` | Server-side bug or crash | maybe, idempotent capabilities only |

---

## 10. Signing reference

```python
# canonical_json(obj) → bytes  (sorted keys, no whitespace, no trailing zeros on floats)

def sign(payload: dict, sk: SigningKey) -> dict:
    p = {k: v for k, v in payload.items() if k != "signature"}
    msg = canonical_json(p)
    sig = sk.sign(msg).signature
    p["signature"] = f"ed25519:{base64url_nopad(sig)}"
    return p

def verify(payload: dict, vk: VerifyKey) -> bool:
    sig_field = payload.get("signature", "")
    if not sig_field.startswith("ed25519:"):
        return False
    sig = base64url_nopad_decode(sig_field[len("ed25519:"):])
    p = {k: v for k, v in payload.items() if k != "signature"}
    msg = canonical_json(p)
    try:
        vk.verify(msg, sig)
        return True
    except BadSignature:
        return False
```

For HTTP requests, the signed payload is the synthetic envelope of §5.1, not the raw body.

---

## 11. Schema hash computation

For a capability descriptor, the schema hash is BLAKE3 of the canonical JSON of:

```json
{
  "name":            "<capability_name>",
  "version":         "<major.minor>",
  "request_schema":  <JSON Schema>,
  "response_schema": <JSON Schema or null>,
  "stream_schema":   <JSON Schema or null>
}
```

If two implementations want to interoperate without reading docs, they MUST produce the same schema hash. Treat schemas as data; never use language-specific Pydantic features in the schema (extra `discriminator`, etc.) without normalising first.

---

## 12. Open questions tracked here

1. **Encrypted chat (Phase 2)** — when added, `chat.message.sent.data.body` becomes ciphertext; envelope (`event_type`, `author`, `recipient`, `lamport`) stays in cleartext. The signature still covers the ciphertext.
2. **Multi-party group chat** — out of scope this release. Reserved event type `chat.group.*`.
3. **Federation manifest** — when added, will look like a community manifest with `peers: []` field. Reserved.
4. **WebSocket upgrade** — when added, the `/bus/v1/call` endpoint will accept an `Upgrade: websocket` header; behaviour is otherwise the same.
5. **Tool calls in `llm.chat`** — declared as Phase 2; the stream frame `tool_call_delta` is reserved.

---

*End of HearthNet Capability Contract v1.0.*
