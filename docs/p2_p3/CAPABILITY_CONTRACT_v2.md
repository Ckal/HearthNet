# HearthNet Capability Contract — Phase 2 additions (v2.0)

**Spec version:** v2.0
**Last touched:** 2026-06-09
**Builds on:** [`../CAPABILITY_CONTRACT.md`](../CAPABILITY_CONTRACT.md) (v1.0)

This document is **additive** to v1.0. Everything in v1.0 still holds unless explicitly overridden here. Bumping a node's `contract_version` to `"2.0"` means: "I implement all of v1 plus the additions below."

---

## 1. Conventions delta

### 1.1 New encoded forms

- **Token format:** `hntoken://v1/<base64-url-nopad of canonical-JSON of token body + signature>`. See [M16 §3](modules/M16-tokens.md).
- **Federation peering blob:** `hnfed://v1/<base64>` — analogous to invite blob, signed by both community roots (cross-sig).
- **Encrypted payload header:** when a chat body is E2E-encrypted, the event's `data.body` becomes a `{"e2e": true, "header": {...}, "ciphertext": "<base64>"}` object. See [M23 §4](modules/M23-e2e-encryption.md).

### 1.2 Sign-over-method choice

Phase 2 capability tokens use the **JWS-flavoured** envelope, not the canonical-JSON envelope. Rationale: tokens are short-lived and frequently passed through HTTP intermediaries; JWS is the lingua franca.

```
hntoken_envelope = base64url(header) + "." + base64url(payload) + "." + base64url(signature)
```

Both forms continue to use Ed25519.

### 1.3 New error codes (additive)

| Code | Meaning |
|------|---------|
| `federation_forbidden` | The caller's community is not federated with ours for this capability |
| `token_invalid` | Token signature failed |
| `token_expired` | Token past `exp` |
| `token_scope_insufficient` | Token does not grant this capability |
| `relay_unreachable` | Configured relay tier is down |
| `e2e_session_missing` | Caller did not establish an X3DH session before sending encrypted message |
| `e2e_decrypt_failed` | Ciphertext could not be decrypted (key mismatch, ratchet drift) |
| `dht_lookup_failed` | DHT lookup timed out before finding sources |
| `not_federated` | Federation manifest does not exist between these communities |

---

## 2. Capability namespace — Phase 2 stable set

Promoted from "reserved" in v1.0:

| Prefix | Now | Defined |
|--------|-----|---------|
| `federation.*` | stable | [M14](modules/M14-federation.md) |
| `ocr.*` | stable | [M17](modules/M17-ocr.md) |
| `trans.*` | stable | [M18](modules/M18-translation.md) |
| `stt.*` `tts.*` | stable | [M19](modules/M19-stt-tts.md) |
| `img.*` | stable | [M20](modules/M20-vision.md) |
| `rerank.*` | stable | [M24](modules/M24-rerank.md) |
| `chat.thread.*` | stable | [M25](modules/M25-group-chat.md) |
| `chat.forward.*` | stable | [M14](modules/M14-federation.md) (via relay) |
| `auth.*` | stable (new) | [M16](modules/M16-tokens.md) |

---

## 3. Complete new capabilities list

| Name | Stability | Stream? | Trust required | Section |
|------|-----------|---------|----------------|---------|
| `federation.peer.add@1.0` | stable | no | anchor (with co-sig) | §4.1 |
| `federation.peer.remove@1.0` | stable | no | anchor (with co-sig) | §4.2 |
| `federation.peer.list@1.0` | stable | no | member | §4.3 |
| `federation.proxy@1.0` | stable | yes | federated | §4.4 |
| `auth.token.issue@1.0` | stable | no | member | §4.5 |
| `auth.token.revoke@1.0` | stable | no | issuer or trusted | §4.6 |
| `auth.token.introspect@1.0` | stable | no | self | §4.7 |
| `ocr.image@1.0` | stable | no | member | §4.8 |
| `ocr.pdf@1.0` | stable | yes (progress) | trusted | §4.9 |
| `trans.text@1.0` | stable | no | member | §4.10 |
| `stt.transcribe@1.0` | stable | yes (segments) | member | §4.11 |
| `tts.synthesize@1.0` | stable | yes (audio chunks) | member | §4.12 |
| `img.describe@1.0` | stable | no | member | §4.13 |
| `img.generate@1.0` | stable | yes (progress) | trusted | §4.14 |
| `rerank.text@1.0` | stable | no | member | §4.15 |
| `chat.thread.create@1.0` | stable | no | member | §4.16 |
| `chat.thread.send@1.0` | stable | no | thread member | §4.17 |
| `chat.thread.history@1.0` | stable | no | thread member | §4.18 |
| `chat.thread.leave@1.0` | stable | no | thread member | §4.19 |
| `chat.forward.put@1.0` | stable | yes | anchor with forward | §4.20 |
| `chat.forward.fetch@1.0` | stable | yes | self | §4.21 |
| `file.put.resume@1.0` | stable | yes | trusted | §4.22 |
| `llm.chat@2.0` (UPDATE) | stable | yes | member | §4.23 |
| `llm.tools.call@1.0` (NEW, used by `llm.chat` tool flow) | stable | no | member | §4.24 |

---

## 4. Per-capability specifications

### 4.1 `federation.peer.add@1.0`

Establish a federation link with another community.

**Request:**
```json
{
  "params": {},
  "input": {
    "client_id":         "01HXR...",
    "peer_community_id": "ed25519:<other community root pubkey>",
    "peer_endpoints":    [{"transport":"https","host":"...","port":7080}],
    "co_signers":        [{"node_id":"...","signature":"..."}, "...", "..."],
    "scope":             {
      "capabilities":   ["rag.query","market.list"],
      "data_visibility":"public_corpora_only"
    },
    "expires_at":        "2027-06-09T00:00:00Z"
  }
}
```

`co_signers` requires `policy.min_signatures_to_federate` (new policy field; default 3, see [M14 §5](modules/M14-federation.md)). The remote community must also have us in their federation manifest before federated calls work.

**Response:**
```json
{"output": {"event_id": "01HXS...", "federation_id": "ed25519:A:ed25519:B"}, "meta": {"ms": 14}}
```

Emits `federation.peer.added` event.

**Errors:** `unauthorized`, `bad_request`, `not_found` (peer endpoints unreachable).

### 4.2 `federation.peer.remove@1.0`

Terminate a federation link.

**Request:**
```json
{
  "params": {},
  "input": {
    "client_id":         "01HXR...",
    "peer_community_id": "ed25519:...",
    "reason":            "policy_violation|unused|mutual",
    "co_signers":        [...]
  }
}
```

Emits `federation.peer.removed`.

### 4.3 `federation.peer.list@1.0`

List active federations.

**Response:**
```json
{
  "output": {
    "peers": [
      {
        "community_id": "ed25519:...",
        "name":         "Geldern Demo",
        "scope":        {"capabilities":["rag.query"]},
        "established_at": "...",
        "expires_at":   "...",
        "last_heartbeat": "..."
      }
    ]
  },
  "meta": {"ms": 2}
}
```

### 4.4 `federation.proxy@1.0`

A federated peer asks *our* community to forward a capability call to one of *our* members. This is how cross-community RAG query works: peer's anchor calls `federation.proxy` on our anchor, which then internally routes to `rag.query` on whichever local node has the corpus.

**Request:**
```json
{
  "params": {"target_capability": "rag.query@1.0"},
  "input": {
    "client_id":   "01HXR...",
    "token":       "hntoken://v1/...",
    "body":        { /* the body of the underlying capability */ }
  }
}
```

**Response:** Whatever the target capability returns. Streams pass through transparently.

The proxy verifies the token's scope includes `target_capability`. Returns `federation_forbidden` otherwise.

### 4.5 `auth.token.issue@1.0`

Issue a capability token.

**Request:**
```json
{
  "params": {},
  "input": {
    "client_id":         "01HXR...",
    "subject":           "ed25519:<recipient NodeID>",
    "scope": {
      "capabilities":   ["rag.query@1.0", "embed.text@1.0"],
      "corpora":        ["niederrhein-emergency"],
      "rate_limit_per_minute": 60
    },
    "ttl_seconds":       3600,
    "audience":          "ed25519:<community_id where token is presented, optional>"
  }
}
```

**Response:**
```json
{
  "output": {"token": "hntoken://v1/eyJhbGc...", "token_id": "01HXS..."},
  "meta": {"ms": 4}
}
```

See [M16](modules/M16-tokens.md) for token body schema.

### 4.6 `auth.token.revoke@1.0`

Revoke a previously-issued token.

**Request:**
```json
{"params": {}, "input": {"client_id":"01HXR...","token_id":"01HXR..."}}
```

Emits `auth.token.revoked` event.

### 4.7 `auth.token.introspect@1.0`

Self-only: check whether a token is still valid.

**Request:** `{"params":{},"input":{"token":"hntoken://v1/..."}}`

**Response:** `{"output":{"active":bool,"scope":{...},"expires_at":"..."},"meta":{...}}`

### 4.8 `ocr.image@1.0`

Extract text from a single image.

**Request:**
```json
{
  "params": {"backend": "tesseract", "languages": ["deu","eng"]},
  "input":  {
    "image_cid": "blake3:...",
    "preprocess": {"deskew": true, "denoise": false}
  }
}
```

**Response:**
```json
{
  "output": {
    "text":   "Trinkwasser ohne Strom ...",
    "blocks": [
      {"text":"Trinkwasser ohne Strom","bbox":[10,20,300,40],"confidence":0.94}
    ],
    "language": "de"
  },
  "meta": {"backend":"tesseract","ms":820}
}
```

### 4.9 `ocr.pdf@1.0`

Extract text from a (scanned) PDF. Streams per-page progress.

**Request:**
```json
{
  "params": {"backend":"multilingual","languages":["deu","lat"]},
  "input":  {
    "doc_cid":     "blake3:...",
    "page_range":  [1, 50],
    "preprocess":  {"deskew": true},
    "store_text":  true
  }
}
```

**Stream frames:**
```
event: progress
data: {"current": 3, "total": 12, "stage": "OCRing page 3"}

event: page
data: {"page": 3, "text": "...", "confidence_mean": 0.91}

event: done
data: {"pages": 12, "stored_cid": "blake3:...", "ms": 18342}
```

If `store_text:true`, the extracted text is stored as a new blob and its CID returned. Useful for piping into `rag.ingest`.

### 4.10 `trans.text@1.0`

Translate between languages.

**Request:**
```json
{
  "params": {"backend":"nllb"},
  "input":  {
    "text":     "Brauche Wasserkanister",
    "from":     "de",
    "to":       "en",
    "domain":   "everyday"
  }
}
```

**Response:**
```json
{
  "output": {"text":"Need water canister", "confidence": 0.97},
  "meta":   {"backend":"nllb","model":"nllb-200-distilled-600M","ms":312}
}
```

Plattdeutsch supported as `nds`. Marketplace UI offers one-click translate on a foreign-language post.

### 4.11 `stt.transcribe@1.0`

Transcribe an audio blob.

**Request:**
```json
{
  "params": {"backend":"whisper","model":"large-v3"},
  "input":  {
    "audio_cid": "blake3:...",
    "language":  "auto",
    "diarize":   false,
    "translate_to_en": false
  }
}
```

**Stream frames:**
```
event: segment
data: {"start": 0.0, "end": 4.2, "text": "Hallo, ich brauche...", "language":"de"}

event: segment
data: {"start": 4.2, "end": 8.1, "text": "Hilfe mit dem Generator."}

event: done
data: {"language":"de","ms":2100,"duration_seconds":18.4}
```

### 4.12 `tts.synthesize@1.0`

Synthesize speech from text.

**Request:**
```json
{
  "params": {"backend":"xtts","voice":"hannes_v1","language":"de"},
  "input":  {
    "text":   "Das Regenwasser muss zuerst gefiltert werden.",
    "speed":  1.0,
    "format": "ogg_vorbis"
  }
}
```

**Stream frames:**
```
event: chunk
data: {"i":0,"size_bytes":16384,"data_b64":"..."}

event: done
data: {"total_bytes":91247,"duration_seconds":4.2,"format":"ogg_vorbis","ms":1832}
```

### 4.13 `img.describe@1.0`

Describe what's in an image.

**Request:**
```json
{
  "params": {"backend":"florence2"},
  "input":  {
    "image_cid": "blake3:...",
    "task":      "detailed_caption",
    "language":  "de"
  }
}
```

`task` ∈ `{"caption","detailed_caption","ocr","objects","tags"}`.

**Response:**
```json
{
  "output": {
    "caption": "Ein Schaltplan einer einfachen Wasserfilteranlage mit ...",
    "tags":    ["schaltplan","wasserfilter","skizze"],
    "objects": [{"label":"pipe","bbox":[10,20,80,90]}]
  },
  "meta": {"backend":"florence2","ms":640}
}
```

### 4.14 `img.generate@1.0`

Generate an image from a text prompt.

**Request:**
```json
{
  "params": {"backend":"flux","model":"flux.1-dev","lora":"local-style-v1"},
  "input":  {
    "prompt":       "ein einfacher schaltplan einer wasserfilteranlage, schwarz auf weiss",
    "negative_prompt": "color, photorealistic",
    "width":        1024,
    "height":       1024,
    "steps":        20,
    "seed":         12345
  }
}
```

**Stream frames:**
```
event: progress
data: {"step":5,"total":20}

event: done
data: {"image_cid":"blake3:...","width":1024,"height":1024,"ms":12800}
```

### 4.15 `rerank.text@1.0`

Rerank a list of documents against a query.

**Request:**
```json
{
  "params": {"model":"BAAI/bge-reranker-v2-m3"},
  "input":  {
    "query":      "Wie reinige ich Regenwasser ohne Strom?",
    "documents":  [
      {"id":"doc1","text":"..."},
      {"id":"doc2","text":"..."}
    ],
    "top_k":      10
  }
}
```

**Response:**
```json
{
  "output": {
    "ranked": [
      {"id":"doc2","score":0.91},
      {"id":"doc1","score":0.42}
    ]
  },
  "meta": {"model":"BAAI/bge-reranker-v2-m3","ms":42}
}
```

### 4.16 `chat.thread.create@1.0`

Create a multi-party thread.

**Request:**
```json
{
  "params": {},
  "input": {
    "client_id":    "01HXR...",
    "name":         "Nachbarschaftshilfe Mai",
    "members":      ["ed25519:...","ed25519:...","ed25519:..."],
    "e2e_enabled":  true
  }
}
```

**Response:** `{"output":{"thread_id":"01HXR...","event_id":"01HXR..."},"meta":{...}}`

### 4.17 `chat.thread.send@1.0`

Send to a thread. Body is E2E-encrypted when `e2e_enabled`.

**Request:**
```json
{
  "params": {"thread_id":"01HXR..."},
  "input": {
    "client_id": "01HXR...",
    "body":      "...",                       // cleartext or {"e2e":true,...} envelope
    "attachments": [{"cid":"blake3:...","name":"..."}]
  }
}
```

### 4.18 `chat.thread.history@1.0`

Self-only history retrieval for a thread.

**Request:** `{"params":{"thread_id":"01HXR..."},"input":{"since_lamport":4000,"limit":200}}`

### 4.19 `chat.thread.leave@1.0`

Leave a thread.

### 4.20 `chat.forward.put@1.0`

Store-and-forward: leave a chat message with an anchor for later delivery.

**Stream initiator pattern** identical to `file.put`. Anchors that opt into the role register this capability.

### 4.21 `chat.forward.fetch@1.0`

Self-only: collect queued messages from an anchor.

### 4.22 `file.put.resume@1.0`

Resume a partial PUT.

**Request:**
```json
{"params":{},"input":{"manifest_cid":"blake3:...","client_id":"01HXR..."}}
```

**Response (server tells client which chunks are missing):**
```
event: ready
data: {"missing":[3,4,5,8]}

(client sends only those chunks)

event: done
data: {"received":4}
```

Server keeps partial transfer state for `FILE_RESUME_PARTIAL_TTL_SECONDS` (1 hour). After that, partial transfers are discarded and client must restart.

### 4.23 `llm.chat@2.0` (update)

Backward-compatible **minor bump** (still `name="llm.chat"`, callers can still ask for `@>=1.0` and be matched). New optional fields:

```json
{
  "params": {"model":"...","modalities":["text","vision"]},
  "input": {
    "messages": [
      {
        "role": "user",
        "content": [
          {"type": "text", "text": "Was siehst du?"},
          {"type": "image", "image_cid": "blake3:..."}
        ]
      }
    ],
    "tools": [
      {
        "name":        "rag.query",
        "description": "Search the niederrhein-emergency corpus",
        "parameters_schema": { /* JSON Schema for tool args */ }
      }
    ],
    "tool_choice": "auto"
  }
}
```

### 4.24 `llm.tools.call@1.0`

When an LLM emits a `tool_call_delta` stream frame followed by `tool_call` end, the **caller** is responsible for executing the tool. To make this composable, the LLM service offers `llm.tools.call` as a convenience that wraps "execute one bus call, return its output as a tool message". Callers MAY use it; the more general flow is to have the orchestrator (UI / agent) handle it.

**Request:**
```json
{
  "params": {},
  "input": {
    "tool_call_id":     "tc_01HXR...",
    "target_capability":"rag.query@1.0",
    "target_body":      { /* the tool's args, validated against the tool's parameters_schema */ }
  }
}
```

**Response:** mirrors target capability's response.

---

## 5. Wire format changes

### 5.1 WebSocket upgrade

For `/bus/v1/call`, clients MAY include:

```
Connection: Upgrade
Upgrade: websocket
Sec-WebSocket-Protocol: hearthnet-bus.v2
```

Server responds with a 101 if it supports WebSocket (Phase 2 nodes do). Once upgraded, the connection is bidirectional and persistent for the life of the request — useful for tool-call loops and streaming RAG.

Frames over WebSocket are the same JSON event-name + data envelope as SSE, just delivered as binary or text WebSocket frames instead of `data:` lines.

See [X06](cross-cutting/X06-websocket.md).

### 5.2 Token-bearer requests

When a caller carries a capability token instead of (or in addition to) a per-request signature:

```
X-HearthNet-Token: hntoken://v1/<base64>
```

The server validates the token (signature, expiry, scope) and uses the token's `subject` as the effective caller for the trust check. The token's `issuer` must be a member of a federated community.

If both `X-HearthNet-Signature` and `X-HearthNet-Token` are present, signature is checked first; token is used to widen scope (e.g. "the caller is a federated peer, but for this single call they presented a token granting access").

### 5.3 Federation routing

When a node receives a call where `X-HearthNet-Community` ≠ our community ID:

1. Look up federation manifest for the calling community.
2. If absent → `not_federated` (404).
3. If present but scope does not include the requested capability → `federation_forbidden` (403).
4. Else, dispatch normally; record federation usage in metrics.

---

## 6. Manifests

### 6.1 Federation manifest (new)

```json
{
  "schema_version": 1,
  "federation_id":  "<community_a>:<community_b>",
  "community_a":    "ed25519:...",
  "community_b":    "ed25519:...",
  "established_at": "2026-06-09T10:00:00Z",
  "expires_at":     "2027-06-09T10:00:00Z",
  "scope": {
    "a_grants_b":   {"capabilities":["rag.query"], "corpora":["public-emergency"]},
    "b_grants_a":   {"capabilities":["rag.query"]}
  },
  "bootstrap_endpoints_a": [{"transport":"https","host":"...","port":7080}],
  "bootstrap_endpoints_b": [{"transport":"https","host":"...","port":7080}],
  "signatures":     {
    "a": {"signed_by":"ed25519:<anchor of A>","signature":"...","co_signers":[{...},{...}]},
    "b": {"signed_by":"ed25519:<anchor of B>","signature":"...","co_signers":[{...},{...}]}
  }
}
```

Both sides must sign with their `min_signatures_to_federate` threshold. The federation manifest lives in **both** communities' event logs.

### 6.2 Token body (new)

JWS-style. Header:

```json
{"alg":"EdDSA","typ":"hntoken","v":1}
```

Payload:

```json
{
  "iss":          "ed25519:<issuer NodeID>",
  "sub":          "ed25519:<subject NodeID>",
  "aud":          "ed25519:<audience community, optional>",
  "iat":          1717939200,
  "exp":          1717942800,
  "jti":          "01HXR...",
  "scope": {
    "capabilities":         ["rag.query@1.0"],
    "params_constraints":   {"corpus":["niederrhein-emergency"]},
    "rate_limit_per_minute": 60
  }
}
```

Signature: Ed25519 over `base64url(header) + "." + base64url(payload)`.

### 6.3 Node manifest delta

Phase 2 nodes set `contract_version: "2.0"`. Additional fields in `capabilities[].params`:

```json
{
  "name": "llm.chat",
  "version": "2.0",
  "params": {
    "model": "...",
    "modalities": ["text","vision"],
    "tools_supported": true,
    "max_tools_per_call": 16,
    "requires_internet": false
  }
}
```

---

## 7. Events (additive to v1.0 §7.2)

### 7.1 New event types

```
federation.peer.added
federation.peer.removed
federation.heartbeat
auth.token.issued
auth.token.revoked
chat.thread.created
chat.thread.member.added
chat.thread.member.removed
chat.thread.message.sent
chat.thread.message.delivered
chat.thread.archived
e2e.prekeys.published
e2e.session.established
e2e.session.broken
file.replication.scheduled
file.replication.completed
ocr.document.indexed
```

### 7.2 Selected schemas

#### `federation.peer.added`

```json
{
  "peer_community_id":  "ed25519:...",
  "federation_id":      "...",
  "scope":              {...},
  "co_signers":         [{...},{...},{...}]
}
```

#### `auth.token.issued`

Stored without the signature payload (just metadata for audit):

```json
{
  "token_id":  "01HXR...",
  "subject":   "ed25519:...",
  "scope":     {...},
  "expires_at":"...",
  "audience":  "ed25519:..."
}
```

#### `auth.token.revoked`

```json
{"token_id":"01HXR...","reason":"manual|policy|compromise"}
```

#### `chat.thread.created`

```json
{
  "thread_id":   "01HXR...",
  "client_id":   "01HXR...",
  "name":        "Nachbarschaftshilfe Mai",
  "members":     ["ed25519:...","ed25519:..."],
  "e2e_enabled": true,
  "ratchet_root_pubkey": "x25519:..."
}
```

#### `chat.thread.message.sent`

```json
{
  "thread_id": "01HXR...",
  "client_id": "01HXR...",
  "body":      {"e2e":true,"header":{...},"ciphertext":"..."} | "<cleartext>",
  "attachments": [...]
}
```

#### `e2e.prekeys.published`

```json
{
  "node_id":   "ed25519:...",
  "identity_pubkey": "x25519:...",
  "signed_prekey": {"pubkey":"x25519:...","signature":"ed25519:..."},
  "one_time_prekeys": ["x25519:...","x25519:...","..."]
}
```

#### `file.replication.scheduled`

```json
{
  "cid":               "blake3:...",
  "desired_copies":    3,
  "current_copies":    1,
  "candidate_holders": ["ed25519:...","ed25519:..."]
}
```

#### `ocr.document.indexed`

```json
{
  "doc_cid":     "blake3:...",
  "text_cid":    "blake3:...",
  "pages":       12,
  "languages":   ["de","la"],
  "ocr_backend": "multilingual"
}
```

### 7.3 Federation events propagate cross-community

Events with `event_type ∈ {federation.*, auth.token.issued, auth.token.revoked}` MAY be cross-published into a federated community's event log. The community receiving such an event records the originating community in `data._source_community`. This is the only case where an event's `community_id` does not equal the log it lives in.

---

## 8. Pub-sub topics (additive)

| Topic | Producer | Subscriber |
|-------|----------|------------|
| `federation.peer.added` | member adding | all members |
| `federation.peer.heartbeat.<peer_community>` | federation client loop | UI |
| `auth.token.issued` | issuer | issuer + subject |
| `chat.thread.message.<thread_id>` | sender | thread members |
| `e2e.prekey.request.<our_short_id>` | sender wanting session | recipient |
| `e2e.session.handshake.<our_short_id>` | initiator | responder |
| `file.replication.request.<cid_prefix>` | replication scheduler | all anchors |
| `mobile.push.<device_id>` | sender | push relay tier (M15) |

---

## 9. Errors — complete delta (additive to v1.0 §9)

| Code | When | Retry? |
|------|------|--------|
| `federation_forbidden` | Caller's community not federated for this capability | no |
| `not_federated` | No federation manifest with caller's community | no |
| `token_invalid` | Token signature bad | no |
| `token_expired` | Token past `exp` | no, request a new token |
| `token_scope_insufficient` | Token does not include this capability | no |
| `token_revoked` | Token id in revoked list | no |
| `relay_unreachable` | Configured relay tier down | yes, exp backoff |
| `e2e_session_missing` | No active X3DH session | yes, after key exchange |
| `e2e_decrypt_failed` | Ciphertext can't be decrypted | no, request rekey |
| `dht_lookup_failed` | DHT did not find sources in time | yes |
| `ratchet_out_of_order` | Message too far out of order; sender must rewind | maybe |

---

## 10. Versioning and migration

### 10.1 Mixed-version mesh

A v1.0 node and a v2.0 node may coexist on the same LAN, but:

- A v2.0 node calling a v1.0 node for a Phase 2 capability gets `not_found` (v1 didn't register it).
- A v1.0 node calling a v2.0 node for a v1 capability works fine (additive contract).
- v2.0 routes around v1.0 nodes for any capability that requires v2 features.

### 10.2 Migration of an existing community

When the founder upgrades to v2.0:

1. New `policy.min_signatures_to_federate` field added with default 3
2. New event types unlock; old log still replays cleanly
3. Existing nodes prompted to upgrade via `community.policy.updated` event
4. After 30 days, federation capabilities won't dispatch to non-upgraded nodes

See `MIGRATION_v1_to_v2.md` (out of band).

---

## 11. Out of scope still (deferred to Phase 3)

- Distributed-tensor inference capabilities (`experimental.distributed_llm.chat`)
- MoE-style expert routing (lives inside the bus as a learned scorer)
- Federated learning capabilities (`fedlearn.*`)
- LoRA long-distance beacons (no capability, hardware-only)
- Evidence-layer integration (`evidence.*` namespace reserved here, defined in Phase 3)
- Conformance test suite as a protocol surface
