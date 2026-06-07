# HearthNet — Spec Set Overview

This directory is the implementation-level specification for HearthNet. It supersedes the design-level PRD for any conflict on the wire format, file layout, or API surface.

The documents are intentionally redundant in some places so each module spec can be read independently during implementation.

---

## 0. How to read this set

Read in this order:

1. **00-OVERVIEW.md** (this file) — module map, dependency graph, build order
2. **GLOSSARY.md** — canonical names for every entity that appears in more than one doc
3. **CAPABILITY_CONTRACT.md** — the wire-level source of truth; everything else must comply
4. **cross-cutting/X01..X04** — concerns that touch every module
5. **modules/M01..M13** — per-module specs in dependency order

Cross-references between documents use the shorthand `[M03 §4.2]` (module 3, section 4.2) or `[CONTRACT §7.1]` (the contract document, section 7.1).

---

## 1. Module map

### Numbered modules (from PRD v2 §20)

| ID  | Module                  | Spec file                                    | Concern                                             |
|-----|-------------------------|----------------------------------------------|------------------------------------------------------|
| M01 | Identity & manifests    | `modules/M01-identity.md`                    | Crypto identity, signing, verification, manifests    |
| M02 | Discovery               | `modules/M02-discovery.md`                   | Finding peers on a LAN or via relay                  |
| M03 | Capability bus          | `modules/M03-bus.md`                         | Routing requests to capabilities                     |
| M04 | LLM service             | `modules/M04-llm.md`                         | Language model inference capabilities                |
| M05 | RAG service             | `modules/M05-rag.md`                         | Retrieval-augmented generation                       |
| M06 | Marketplace service     | `modules/M06-marketplace.md`                 | Community posts, offers, requests                    |
| M07 | File / blobs            | `modules/M07-file-blobs.md`                  | Content-addressed storage and transfer               |
| M08 | UI                      | `modules/M08-ui.md`                          | Gradio dashboard + topology viz + mobile             |
| M09 | Emergency detector      | `modules/M09-emergency.md`                   | Internet up/down detection + mode transitions        |
| M10 | Chat service            | `modules/M10-chat.md`                        | Direct messages + store-and-forward                  |
| M11 | Embedding service       | `modules/M11-embedding.md`                   | Text and image embedding capabilities                |
| M12 | CLI                     | `modules/M12-cli.md`                         | `hearthnet` command-line entry points                |
| M13 | Onboarding              | `modules/M13-onboarding.md`                  | First-run UX, invite QR, key generation flow         |

### Cross-cutting modules

| ID  | Module          | Spec file                              | Concern                                             |
|-----|-----------------|----------------------------------------|------------------------------------------------------|
| X01 | Transport       | `cross-cutting/X01-transport.md`       | HTTP server, HTTP client, TLS, streaming, backpressure |
| X02 | Events          | `cross-cutting/X02-events.md`          | Event log, Lamport clocks, snapshots, gossip sync    |
| X03 | Observability   | `cross-cutting/X03-observability.md`   | Logging, metrics, tracing, self-diagnostics          |
| X04 | Config          | `cross-cutting/X04-config.md`          | Configuration loading and validation                 |

---

## 2. Dependency graph

```
                      ┌──────────┐
                      │  config  │  X04
                      └────┬─────┘
                           │ (everyone reads it)
            ┌──────────────┴──────────────┐
            ▼                             ▼
       ┌─────────┐                  ┌─────────────┐
       │ identity│  M01             │observability│  X03
       └────┬────┘                  └─────────────┘
            │
   ┌────────┼────────────┬────────────┐
   ▼        ▼            ▼            ▼
┌──────┐ ┌─────────┐ ┌─────────┐ ┌──────────┐
│events│ │discovery│ │transport│ │  blobs   │   X02 / M02 / X01 / part-of-M07
└──┬───┘ └────┬────┘ └────┬────┘ └────┬─────┘
   │          │           │           │
   │          └───────┬───┘           │
   │                  ▼               │
   │             ┌─────────┐          │
   │             │   bus   │  M03     │
   │             └────┬────┘          │
   │                  │               │
   │   ┌─────────┬────┴────┬────────┐ │
   │   ▼         ▼         ▼        ▼ ▼
   │ ┌─────┐ ┌──────┐ ┌────────┐ ┌────────┐
   │ │ llm │ │embed │ │  rag   │ │  file  │   M04 / M11 / M05 / M07
   │ └─────┘ └──┬───┘ └───┬────┘ └────────┘
   │            │         │
   │            └─────────┘   (rag uses embed)
   │
   │  ┌────────────┐  ┌──────┐
   ├─►│ marketplace│  │ chat │   M06 / M10
   │  └────────────┘  └──────┘
   │            │         │
   └────────────┘         │
                          │
                ┌─────────▼──────────┐
                │     emergency      │   M09
                └────────┬───────────┘
                         │
                ┌────────▼───────────┐
                │        ui          │   M08
                └────────────────────┘
                         │
                ┌────────▼───────────┐
                │   onboarding       │   M13
                └────────────────────┘
                         │
                ┌────────▼───────────┐
                │        cli         │   M12
                └────────────────────┘
```

Hard rules:

- **No service imports from another service.** Services talk to each other only via the bus.
- **No layer below the bus imports anything above it.** Transport never imports a service; identity never imports the bus.
- **The bus does not know what services exist** at build time. Services register themselves at startup.
- **UI never imports a service directly.** It calls capabilities via the bus.

---

## 3. File tree (Python package layout)

```
hearthnet/
├── __init__.py
├── __main__.py                       # python -m hearthnet → cli.main()
├── version.py                        # __version__ = "0.1.0"
│
├── config.py                         # X04
│
├── identity/                         # M01
│   ├── __init__.py
│   ├── keys.py
│   ├── manifest.py
│   └── tokens.py                     # Phase 2
│
├── observability/                    # X03
│   ├── __init__.py
│   ├── logging.py
│   ├── metrics.py
│   ├── tracing.py
│   └── doctor.py
│
├── events/                           # X02
│   ├── __init__.py
│   ├── log.py
│   ├── lamport.py
│   ├── types.py
│   ├── replay.py
│   ├── snapshot.py
│   └── sync.py
│
├── discovery/                        # M02
│   ├── __init__.py
│   ├── mdns.py
│   ├── udp.py
│   ├── peers.py                      # peer registry (in-memory)
│   └── relay.py                      # Phase 2
│
├── transport/                        # X01
│   ├── __init__.py
│   ├── server.py
│   ├── client.py
│   ├── streams.py
│   ├── backpressure.py
│   └── tls.py
│
├── blobs/                            # M07 (the storage half)
│   ├── __init__.py
│   ├── store.py
│   ├── chunker.py
│   └── transfer.py
│
├── bus/                              # M03
│   ├── __init__.py
│   ├── capability.py
│   ├── registry.py
│   ├── router.py
│   ├── health.py
│   ├── schema.py
│   └── trace.py
│
├── services/                         # L4
│   ├── __init__.py
│   ├── base.py
│   ├── llm/                          # M04
│   │   ├── __init__.py
│   │   ├── service.py
│   │   ├── tokenizers.py
│   │   └── backends/
│   │       ├── __init__.py
│   │       ├── base.py
│   │       ├── llama_cpp.py
│   │       ├── ollama.py
│   │       ├── lmstudio.py
│   │       ├── hf_api.py
│   │       └── anthropic_api.py
│   ├── embedding/                    # M11
│   │   ├── __init__.py
│   │   ├── service.py
│   │   └── backends.py
│   ├── rag/                          # M05
│   │   ├── __init__.py
│   │   ├── service.py
│   │   ├── chunker.py
│   │   ├── ingest.py
│   │   └── store.py
│   ├── file/                         # M07 (the service half)
│   │   ├── __init__.py
│   │   └── service.py
│   ├── marketplace/                  # M06
│   │   ├── __init__.py
│   │   ├── service.py
│   │   ├── post.py
│   │   └── views.py
│   └── chat/                         # M10
│       ├── __init__.py
│       ├── service.py
│       ├── delivery.py
│       └── views.py
│
├── emergency/                        # M09
│   ├── __init__.py
│   ├── detector.py
│   └── state.py
│
├── ui/                               # M8 + M13
│   ├── __init__.py
│   ├── app.py
│   ├── topology.py
│   ├── theme.py
│   ├── onboarding.py                 # M13
│   ├── tabs/
│   │   ├── __init__.py
│   │   ├── ask.py
│   │   ├── chat.py
│   │   ├── marketplace.py
│   │   ├── files.py
│   │   ├── emergency.py
│   │   └── settings.py
│   └── mobile/                       # static assets
│       ├── index.html
│       ├── app.js
│       └── style.css
│
├── cli.py                            # M12
├── node.py                           # Orchestrator (composes everything)
└── doctor.py                         # (re-export of observability.doctor)

tests/
├── unit/                             # per-module
│   ├── test_identity_keys.py
│   ├── test_identity_manifest.py
│   ├── test_events_log.py
│   ├── ...
└── integration/                      # multi-node
    ├── test_three_node_mesh.py
    ├── test_emergency_mode.py
    └── test_rejoin_sync.py
```

---

## 4. Canonical conventions

### 4.1 Type aliases (use these names everywhere)

```python
NodeID         = str        # "ed25519:XXXX-XXXX-XXXX-XXXX"
CommunityID    = str        # "ed25519:..."
CapabilityName = str        # "llm.chat"
Version        = tuple[int, int]   # (1, 0)
Lamport        = int
CID            = str        # "blake3:..."
EventID        = str        # ULID
TraceID        = str        # ULID
SchemaHash     = str        # "blake3:..."
WallClock      = str        # RFC 3339 UTC: "2026-05-26T08:14:22Z"
Signature      = str        # "ed25519:<base64-url-nopad>"
Topic          = str        # "marketplace.post.created"
ErrorCode      = Literal[
    "not_found", "capacity_exceeded", "schema_mismatch", "unauthorized",
    "revoked", "internal_error", "not_implemented", "timeout", "partition",
    "invalid_signature", "expired", "rate_limited", "bad_request",
]
TrustLevel     = Literal["unknown", "member", "trusted", "anchor"]
Profile        = Literal["anchor", "hearth", "spark", "bridge"]
Stability      = Literal["experimental", "beta", "stable"]
```

These are defined in `hearthnet.types` and re-exported by every module that uses them. Never invent a synonym.

### 4.2 Naming

- Functions: `snake_case`, verb-first (`load_keys`, `verify_signature`, `route_request`)
- Classes: `PascalCase`, noun (`NodeManifest`, `CapabilityBus`, `RagService`)
- Constants: `SCREAMING_SNAKE` (`MANIFEST_TTL_SECONDS`)
- Module-private: leading underscore (`_compute_canonical_json`)
- Async functions: same naming as sync, no `async_` prefix
- Protocols / interfaces: `PascalCase` ending in capability noun (`LlmBackend`, `Service`)

### 4.3 Error handling

- All errors that cross a process boundary become an `HearthNetError` with an `ErrorCode`
- All errors that stay in-process are domain exceptions inheriting from `HearthNetError`
- Never raise `RuntimeError` or bare `Exception` in production code
- Logging exceptions: always with `exc_info=True` so traceback survives

### 4.4 Async vs sync

- I/O is async (asyncio)
- CPU-bound work (PDF parsing, embedding) runs in `asyncio.to_thread` or a dedicated process pool
- Public APIs are async unless explicitly noted (`load_keys` is sync, returns from disk)

### 4.5 Time

- All wall-clock timestamps in events: RFC 3339 UTC, e.g. `2026-05-26T08:14:22Z`
- All durations: integers in seconds, named `*_seconds` (never `*_secs`, `*_s`)
- Logical ordering: Lamport clocks; wall clock is advisory only

### 4.6 Sizes

- Bytes: integers, named `*_bytes`
- KB/MB/GB shown to users only at the UI layer, never in protocol/event payloads

---

## 5. Build order (hackathon-aligned)

Strictly follow this order. Each step is independently demoable.

| Step | Modules built                          | What you can demo            |
|------|----------------------------------------|------------------------------|
| 1    | X04 (config), X03 (logging only)       | Process boots, logs to file  |
| 2    | M01 (identity, manifests)              | `hearthnet init` works       |
| 3    | X02 (events log + Lamport, no sync)    | Marketplace events persist   |
| 4    | X01 (transport, server only)           | Two nodes can ping each other|
| 5    | M02 (discovery, mDNS only)             | Two nodes find each other    |
| 6    | M03 (bus with fake echo service)       | A capability call round-trips|
| 7    | M04 (LLM, llama.cpp or LM Studio backend) | Real LLM call across nodes |
| 8    | M11 (embeddings)                       | Embed text via the bus       |
| 9    | M05 (RAG)                              | RAG-grounded answer          |
| 10   | M08 (UI shell + topology viz)          | Visible mesh, visible routing|
| 11   | M09 (emergency detector)               | Banner toggles on cable yank |
| 12   | M06 (marketplace)                      | Post visible across nodes    |
| 13   | M10 (chat)                             | Cross-node DM                |
| 14   | M07 (file/blobs)                       | CID-addressed file transfer  |
| 15   | M12 (CLI), M13 (onboarding)            | First-run UX polished        |
| 16   | X02 sync, X03 metrics, X03 doctor      | Production-ish polish        |

---

## 6. Versioning of this spec set

Every spec file carries a header `Spec version: vX.Y` and a `Last touched: <date>`. Bump the minor on additive changes, the major on breaking changes. The contract document's version is the version everyone else complies with — module specs may lag by one minor.

The Python package version (`hearthnet.version.__version__`) and the contract version are independent. The contract version appears in the `version` field of every node manifest and is checked at handshake.

---

## 7. Out-of-band documents

Not in this spec set but referenced:

- **PRD v2** (`../HEARTHNET_PRD_v2.md`) — vision, scope, monetisation, phased roadmap
- **README** (in repo root, written later) — user-facing quickstart
- **THREAT_MODEL.md** (Phase 2) — formal security write-up
- **DEPLOYMENT.md** (Phase 2) — for the appliance and relay-tier operators
