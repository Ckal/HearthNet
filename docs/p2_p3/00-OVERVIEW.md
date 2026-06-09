# HearthNet Phase 2 — Spec Set Overview

**Phase 2 scope:** post-hackathon, 1–3 months of work. Hardens the MVP into something other communities can adopt.

**Stance toward Phase 1:** strictly additive. Phase 1 specs are immutable from Phase 2's view. New modules plug into the bus; nothing in Phase 1 needs rewriting. Where a Phase 1 module is "extended", it is *extended* — same public API, new capabilities or backends added behind the existing facade.

---

## 0. What changes vs Phase 1

| Concern | Phase 1 (MVP) | Phase 2 |
|---------|---------------|---------|
| Discovery | mDNS + UDP (LAN only) | + DHT (cross-LAN), + relay-assisted NAT traversal |
| Transport | HTTP/1.1 + SSE long-poll pubsub | + WebSocket upgrade for bidirectional + pubsub |
| Trust | Per-request signing | + Capability tokens (delegation, federation) |
| Cross-community | Out of scope | Federation: signed peering, scoped capability access |
| Encryption | TLS-in-transit + signed-at-rest within community | + E2E (X25519 + ChaCha20-Poly1305) for chat & optionally files |
| Chat | 1:1 only | + Group chat (`chat.thread.*`), + store-and-forward via anchors |
| LLM | Text only | + Vision (`llm.chat` with image content), + Tool calls (`tool_call_delta`) |
| RAG | Digital PDFs | + OCR for scanned PDFs and images, + reranking |
| Services | LLM, embed, RAG, file, market, chat | + OCR, Translation, STT, TTS, Image generation, Rerank |
| Mobile | Web view served by anchor | + Native client (Flutter/RN) with push via relay tier |
| Files | Direct fetch on demand | + Resumable PUT, + Background replication, + At-rest encryption |
| Relay | None | + Hosted relay tier for NAT traversal, federation discovery, push |
| Observability | Local Prometheus + ring buffer + optional Trackio | + OTLP export, + Federated metrics aggregation |

---

## 1. Module map (Phase 2 additions)

### New numbered modules

| ID  | Module                       | Spec file                              | Concern                                              |
|-----|------------------------------|----------------------------------------|-------------------------------------------------------|
| M14 | Federation                   | `modules/M14-federation.md`            | Cross-community trust, federation manifests, scoped access |
| M15 | Relay Tier                   | `modules/M15-relay-tier.md`            | Hosted HTTPS relay (NAT traversal, federation discovery, mobile push) |
| M16 | Capability Tokens            | `modules/M16-tokens.md`                | Short-lived delegation tokens (OAuth-flavoured)       |
| M17 | OCR Service                  | `modules/M17-ocr.md`                   | `ocr.image`, `ocr.pdf` — Tesseract / TrOCR / multilingual |
| M18 | Translation Service          | `modules/M18-translation.md`           | `trans.text` — NLLB-backed, DE↔EN↔Plattdeutsch         |
| M19 | Speech I/O                   | `modules/M19-stt-tts.md`               | `stt.transcribe` (Whisper), `tts.synthesize` (XTTS/Edge) |
| M20 | Vision Services              | `modules/M20-vision.md`                | `img.describe`, `img.generate`, multimodal LLM input  |
| M21 | Tool Calls                   | `modules/M21-tool-calls.md`            | `tool_call_delta` frames, OpenAI/Anthropic-compatible |
| M22 | Mobile Native                | `modules/M22-mobile-native.md`         | Flutter/RN client with push                            |
| M23 | E2E Encryption               | `modules/M23-e2e-encryption.md`        | X25519 + ChaCha20-Poly1305 for chat (and optional files) |
| M24 | Reranking                    | `modules/M24-rerank.md`                | `rerank.text` — BGE-reranker, used by RAG and search   |
| M25 | Group Chat                   | `modules/M25-group-chat.md`            | `chat.thread.*` — multi-party conversations            |

### New cross-cutting modules

| ID  | Module          | Spec file                              | Concern                                                |
|-----|-----------------|----------------------------------------|---------------------------------------------------------|
| X05 | DHT             | `cross-cutting/X05-dht.md`             | Kademlia-style cross-LAN peer + content discovery       |
| X06 | WebSocket       | `cross-cutting/X06-websocket.md`       | Bidirectional upgrade for `/bus/v1/call` and `/pubsub`  |
| X07 | Federated Metrics | `cross-cutting/X07-federated-metrics.md` | Optional OTLP export + per-community aggregation       |

### Modifications to Phase 1 modules

These do not get new spec files — Phase 1 spec is *extended* in place at next major. The Phase 1 IMPLEMENTATION_REFERENCE will gain entries; flagged in [`IMPLEMENTATION_REFERENCE.md`](IMPLEMENTATION_REFERENCE.md) §0.

| Phase 1 module | Extension |
|----------------|-----------|
| M04 LLM        | New backends gain multimodal + tools support; descriptors carry `modalities`, `tools_supported` flags |
| M05 RAG        | Auto-reindex on embedding model change; hybrid (keyword+dense) search; `rerank.text` integration |
| M07 File/Blobs | Resumable PUT (server-side partial-transfer index); background replication; at-rest encryption envelope |
| M10 Chat       | Calls into M23 for encryption; calls into M25 for group threads |
| M02 Discovery  | Calls into X05 DHT when peers not found via mDNS/UDP |
| X01 Transport  | Calls into X06 WebSocket on `Upgrade: websocket` header |
| M09 Emergency  | Phase-2 captive-portal probe |

---

## 2. Dependency graph (Phase 2 additions on top of Phase 1)

```
                  ┌──────────────────────────────────────────────┐
                  │              Phase 1 (unchanged)             │
                  │  X04 X03 X02 X01 M01..M13                    │
                  └────┬─────────┬───────┬────────┬──────────────┘
                       │         │       │        │
                       ▼         ▼       ▼        ▼
                 ┌─────────┐ ┌─────┐ ┌─────────┐ ┌─────────┐
                 │  X05    │ │ X06 │ │  X07    │ │  M16    │
                 │  DHT    │ │ WS  │ │  Fed-M  │ │ Tokens  │
                 └────┬────┘ └──┬──┘ └─────────┘ └────┬────┘
                      │         │                     │
                      └─────┬───┘                     │
                            ▼                         ▼
                       ┌────────┐                ┌────────┐
                       │  M14   │◄───────────────┤  M15   │
                       │Federat.│                │ Relay  │
                       └───┬────┘                └────────┘
                           │
                           ▼
                       ┌────────┐
                       │  M22   │
                       │ Mobile │
                       └────────┘

           ┌─── Independent services (each plug into the bus) ───┐
           │   M17 OCR   M18 Trans   M19 STT/TTS   M20 Vision   │
           │   M21 Tools (extends M04)             M24 Rerank   │
           └───────────────────────────────────────────────────┘

       ┌─── Chat extensions ───┐
       │  M23 E2E              │
       │  M25 Group            │
       └───────────────────────┘
```

Hard rules carried over from Phase 1:
- No service imports another service. Talk via the bus.
- No layer below the bus imports anything above it.

---

## 3. File tree additions

```
hearthnet/
├── federation/                            # M14
│   ├── __init__.py
│   ├── manifest.py
│   ├── peering.py
│   └── relay_client.py
│
├── relay/                                 # M15  (separate deployable, lives in same repo)
│   ├── __init__.py
│   ├── server.py
│   ├── nat_traversal.py
│   ├── push.py
│   └── tier.py
│
├── identity/
│   └── tokens.py                          # M16 (now real, not stub)
│
├── dht/                                   # X05
│   ├── __init__.py
│   ├── kademlia.py
│   ├── routing.py
│   └── storage.py
│
├── transport/
│   └── websocket.py                       # X06
│
├── observability/
│   └── federated.py                       # X07
│
├── crypto/                                # M23 (new top-level)
│   ├── __init__.py
│   ├── ratchet.py
│   ├── kem.py
│   └── envelope.py
│
├── services/
│   ├── ocr/                               # M17
│   │   ├── __init__.py
│   │   ├── service.py
│   │   └── backends/
│   │       ├── tesseract.py
│   │       ├── trocr.py
│   │       └── multilingual.py
│   ├── translation/                       # M18
│   │   ├── __init__.py
│   │   ├── service.py
│   │   └── backends/
│   │       ├── nllb.py
│   │       └── plattdeutsch.py
│   ├── speech/                            # M19
│   │   ├── __init__.py
│   │   ├── stt_service.py
│   │   ├── tts_service.py
│   │   └── backends/
│   │       ├── whisper.py
│   │       ├── xtts.py
│   │       └── edge_tts.py
│   ├── image/                             # M20
│   │   ├── __init__.py
│   │   ├── describe_service.py
│   │   ├── generate_service.py
│   │   └── backends/
│   │       ├── florence2.py
│   │       ├── minicpm_v.py
│   │       └── flux.py
│   ├── rerank/                            # M24
│   │   ├── __init__.py
│   │   ├── service.py
│   │   └── backends/
│   │       └── bge_reranker.py
│   ├── llm/
│   │   └── tools.py                       # M21 (extends M04)
│   ├── chat/
│   │   ├── encryption.py                  # M23 hook
│   │   ├── thread_service.py              # M25
│   │   └── thread_views.py                # M25
│   └── file/
│       ├── resume.py                      # P7 extension
│       └── replication.py                 # P7 extension

mobile-native/                             # M22 — separate codebase, Flutter project
└── (lives in /mobile-native, not in the Python package)
```

---

## 4. Canonical conventions (delta from Phase 1)

### 4.1 New type aliases

```python
# additions to hearthnet/types.py

TokenID         = str        # ULID
ThreadID        = str        # ULID
FederationID    = str        # composite: "<community_a>:<community_b>"
TensorChunkID   = str        # blake3:<hex>, used in M25/X07 phase-3 only
PushDeviceID    = str        # opaque, assigned by relay tier
RatchetEpoch    = int        # per-thread monotonic
EncryptedPayload = bytes     # ciphertext, base64 in JSON

# Extended Literal types:
TrustLevel      = Literal["unknown","member","trusted","anchor","federated"]
Stability       = Literal["experimental","beta","stable","deprecated"]
```

### 4.2 New constants

```python
# additions to hearthnet/constants.py

TOKEN_DEFAULT_TTL_SECONDS              = 3600
TOKEN_MAX_TTL_SECONDS                  = 86400
FEDERATION_MANIFEST_TTL_SECONDS        = 86400
FEDERATION_HEARTBEAT_SECONDS           = 300
DHT_REPLICATION_K                      = 8           # bucket size
DHT_ALPHA                              = 3           # concurrent lookups
DHT_REFRESH_SECONDS                    = 3600
DHT_REPUBLISH_SECONDS                  = 86400
WEBSOCKET_PING_SECONDS                 = 30
WEBSOCKET_IDLE_CLOSE_SECONDS           = 120
RELAY_REGISTRATION_TTL_SECONDS         = 7200
RELAY_PUSH_RETRY_MAX                   = 5
E2E_RATCHET_MAX_OUT_OF_ORDER           = 32
E2E_RATCHET_REKEY_AFTER_MESSAGES       = 100
E2E_PREKEY_BUNDLE_SIZE                 = 20
OCR_DEFAULT_DPI                        = 300
OCR_MAX_PAGES_PER_REQUEST              = 50
TRANSLATION_MAX_CHARS                  = 4000
STT_MAX_AUDIO_SECONDS                  = 300
TTS_MAX_TEXT_CHARS                     = 5000
RERANK_MAX_DOCS                        = 100
FILE_REPLICATION_DESIRED_COPIES        = 3
FILE_RESUME_PARTIAL_TTL_SECONDS        = 3600
```

### 4.3 Capability namespace allocations (Phase 2 promotes from reserved)

| Prefix | Status in Phase 1 | Status in Phase 2 |
|--------|-------------------|---------------------|
| `federation.*` | beta (reserved) | stable |
| `ocr.*` | reserved | stable |
| `trans.*` | reserved | stable |
| `stt.*` `tts.*` | reserved | stable |
| `img.*` | reserved | stable |
| `rerank.*` | (new) | stable |
| `chat.thread.*` | reserved | stable |
| `chat.forward.*` | reserved | stable |
| `file.put.resume@1.0` | (new) | stable |

---

## 5. Build order (Phase 2)

| Step | Modules / extensions             | What you can demo                              |
|------|----------------------------------|-------------------------------------------------|
| P2-1 | M16 Tokens                       | Delegate one capability call via a token        |
| P2-2 | X05 DHT (basic)                  | Two LANs find each other through a public DHT   |
| P2-3 | M14 Federation                   | Two communities cross-sign, query each other    |
| P2-4 | M15 Relay Tier                   | NAT'd peers reach each other via your relay     |
| P2-5 | X06 WebSocket                    | Lower-latency pubsub                            |
| P2-6 | M24 Rerank                       | RAG queries get better answers                  |
| P2-7 | M17 OCR + M05 RAG hook           | Scanned PDFs become searchable                  |
| P2-8 | M18 Translation                  | DE → EN of a marketplace post                   |
| P2-9 | M19 STT/TTS                      | "Sprich mit HearthNet" voice query              |
| P2-10 | M21 Tool calls + M04 ext        | LLM can call `rag.query` as a tool              |
| P2-11 | M20 Vision                       | "Was siehst du auf diesem Bild?"                |
| P2-12 | M23 E2E + M10 ext                | Chat is now end-to-end encrypted                |
| P2-13 | M25 Group chat                   | Three-way conversation                          |
| P2-14 | M07 ext (resume, replication, encrypt) | Bigger files, more resilient |
| P2-15 | M22 Mobile native                | iOS / Android app on a real phone               |
| P2-16 | X07 Federated metrics + observability polish | Real dashboards for operators |

Each step is independently demoable. Each gates on no Phase 1 changes — they all attach via the bus.

---

## 6. Spec versioning

- Capability Contract bumps to **v2.0** (additive within phase 2; major bump only on breaking changes).
- Contract version in node manifests becomes `"2.0"`; peers running Phase 1 see `contract_version=2.0` and reject the manifest with `schema_mismatch` unless they have a compatibility shim.
- **Compatibility shim:** a Phase 1 node may negotiate down by serving `/manifest?contract_version=1.0`. Optional. Phase 2 SHOULD include the shim for one minor release window.

---

## 7. What is intentionally NOT in Phase 2

Pushed to Phase 3 (see [`../phase-3/00-OVERVIEW.md`](../phase-3/00-OVERVIEW.md)):

- Distributed-tensor inference (Petals-style)
- MoE expert routing
- Federated learning on LoRA layers
- LoRA long-distance beacons
- EBKH evidence layer integration
- Civil-defence pilot
- Protocol-standardisation work
- Conformance test suite for multi-implementation interop

---

## 8. Out-of-band documents (Phase 2)

- **THREAT_MODEL_v2.md** — formal security write-up for federation + E2E + tokens
- **RELAY_OPERATIONS.md** — for whoever runs `relay.hearthnet.de` (likely Christof on Hetzner)
- **MOBILE_BUILD.md** — Flutter build, code-signing, store-submission notes
- **MIGRATION_v1_to_v2.md** — for existing Phase-1 communities upgrading
