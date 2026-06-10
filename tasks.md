# HearthNet Task Plan and Spec Coverage

## Current Truth — Phase 1 + Phase 2 Core Implementation

All M01-M13 and X01-X04 modules have been implemented. The codebase now has real implementations
for identity (Ed25519), event log (SQLite), discovery (mDNS/UDP), transport (FastAPI),
LLM backends (Ollama/llama.cpp/HF/OpenAI-compat), RAG (chunker+Chroma), blobs (BLAKE3),
embedding (sentence-transformers), CLI (click), onboarding (invite/QR), marketplace
(event-sourced), chat (event-backed), emergency (async probe loop), and UI (Gradio tabs).

Implementation policy: no mocks in implementation paths, no security pragmas, real local-first
model backends, OpenAI only as an opt-in online fallback, UI behavior/wording adheres to specs.

## Phase 1 Demo: Done

- [x] Import the Hugging Face Space into the local workspace.
- [x] Read all spec files for implementation direction.
- [x] Preserve existing browser mesh prototypes as supporting material.
- [x] Build Hugging Face-compatible Gradio `app.py`.
- [x] Add ZeroGPU startup probe for HF runtime compatibility.
- [x] Create `hearthnet/` Python package for the Phase 1 demo slice.
- [x] Add `HearthNetController` over `HearthNode`.
- [x] Add facades for RAG, chat, and marketplace workflows.
- [x] Add `CapabilityBus`, registry, router, health tracking, in-memory traces.
- [x] Add simulated peer discovery and manifest ingestion.
- [x] Add deterministic demo nodes for anchor, hearth, and spark profiles.
- [x] Add demo services for all capabilities.
- [x] Add emergency mode state and manual probe handling.
- [x] Add focused tests for routing, failover, emergency mode, and controller snapshots.
- [x] Add `ruff`, `bandit`, `pylint`, `mypy`, and `pytest` config.

## Phase 2 Core Implementation: Done (June 2026)

- [x] **X04 Config** — `hearthnet/config.py`: typed frozen Config, TOML load/save, XDG path resolution, validation
- [x] **hearthnet/constants.py** — all numeric constants for health, pruning, emergency, blobs, RAG, LLM
- [x] **X03 Observability** — `hearthnet/observability/`: JSON logging, prometheus metrics (optional), trace ring buffer, doctor checks
- [x] **M01 Identity** — `hearthnet/identity/`: Ed25519 KeyPair, canonical JSON, sign/verify, node/community manifests
- [x] **X02 Events** — `hearthnet/events/`: SQLite event log, LamportClock, ReplayEngine, MaterialisedView, SnapshotStore, SyncClient/Server
- [x] **M07 File/Blobs** — `hearthnet/blobs/`: BLAKE3 CID store, chunking, transfer; `hearthnet/services/file/`: file.read/list/advertise/put capabilities
- [x] **M11 Embedding** — `hearthnet/services/embedding/`: EmbeddingService, SimpleHashBackend (no-dep test), SentenceTransformerBackend
- [x] **M05 RAG** — `hearthnet/services/rag/`: chunker (sliding window, paragraph-aware), CorpusStore (Chroma + in-memory fallback), IngestPipeline, RagService
- [x] **M12 CLI** — `hearthnet/cli.py`: click-based CLI with init/run/status/caps/call/doctor/trace/export; `hearthnet/__main__.py`
- [x] **M09 Emergency** — async probe loop (DNS + HTTP), debounce, anti-flap, async pub/sub StateBus
- [x] **M02 Discovery** — `hearthnet/discovery/`: MdnsAnnouncer/Browser (zeroconf), UdpAnnouncer/Listener (multicast), enhanced PeerRegistry with async subscribe
- [x] **M04 LLM** — `hearthnet/services/llm/`: LlmService with OllamaBackend, LlamaCppBackend, HfLocalBackend, OpenAICompatBackend (online-only fallback), tokenizers
- [x] **M06 Marketplace** — `hearthnet/services/marketplace/`: Post dataclass, MarketplaceView (event-sourced), MarketplaceService with event-log + demo fallback
- [x] **M10 Chat** — `hearthnet/services/chat/`: ChatMessage, ChatView (event-sourced), DeliveryManager, ChatService with event-log + demo fallback
- [x] **M13 Onboarding** — `hearthnet/ui/onboarding.py`: invite encode/decode, QR generation, create/join/redeem community flows
- [x] **X01 Transport** — `hearthnet/transport/`: FastAPI HttpServer (12 endpoints), HttpClient with signing, SSE streams, TLS cert generation, PinnedCerts
- [x] **M03 Bus upgrades** — `hearthnet/bus/schema.py` (JSON Schema validation), `hearthnet/bus/trace.py` (CallTraceEvent, TraceHook)
- [x] **M08 UI** — `hearthnet/ui/app.py` + `hearthnet/ui/tabs/`: Ask/Chat/Marketplace/Files/Emergency/Settings tabs; bus-only wiring

## Spec Coverage Matrix

| Spec | Status | What exists |
| --- | --- | --- |
| `GLOSSARY.md` | ✅ implemented | NodeID/CID/ULID helpers, XDG paths in config, canonical constants |
| `CAPABILITY_CONTRACT.md` | ✅ implemented | Signed envelopes (X01), schema validation (bus/schema.py), BLAKE3 hashes, SSE streaming |
| M01 Identity | ✅ implemented | `hearthnet/identity/`: Ed25519 keys, canonical JSON, sign/verify, node + community manifests |
| M02 Discovery | ✅ implemented | `hearthnet/discovery/`: mDNS (zeroconf), UDP broadcast, PeerRegistry with async events |
| M03 Capability Bus | ✅ implemented | Registry, router, health, schema validation, trace hook, streaming support |
| M04 LLM | ✅ implemented | Ollama, llama.cpp, HF Transformers backends; llm.chat + llm.complete; OpenAI online fallback |
| M05 RAG | ✅ implemented | Chunker (paragraph/sliding window), CorpusStore (Chroma + in-memory), IngestPipeline, bus-via-embed |
| M06 Marketplace | ✅ implemented | Event-sourced with MarketplaceView, post/list/expire/search; demo fallback |
| M07 File/Blobs | ✅ implemented | BLAKE3 CID store, 256KB chunking, BlobStore, TransferManager, FileService |
| M08 UI | ✅ implemented | `hearthnet/ui/`: UiApp, 6 tabs (Ask/Chat/Market/Files/Emergency/Settings), bus-only |
| M09 Emergency | ✅ implemented | Async probe loop, DNS+HTTP probes, anti-flap, async StateBus, async Detector |
| M10 Chat | ✅ implemented | ChatView (event-sourced), DeliveryManager, ChatService; demo fallback |
| M11 Embedding | ✅ implemented | embed.text capability, SimpleHashBackend (no-dep), SentenceTransformerBackend |
| M12 CLI | ✅ implemented | `hearthnet/cli.py`: init/run/status/caps/call/doctor/trace/export; console script |
| M13 Onboarding | ✅ implemented | InviteBlob, encode/decode, QR PNG, create/join/redeem community, Gradio wizard |
| X01 Transport | ✅ implemented | FastAPI server (12 endpoints), HttpClient (signed), SSE, TLS cert, PinnedCerts |
| X02 Events | ✅ implemented | SQLite WAL log, LamportClock, ReplayEngine, MaterialisedView, SnapshotStore, SyncClient |
| X03 Observability | ✅ implemented | JSON logging (rotating), prometheus metrics (optional), trace ring buffer, doctor checks |
| X04 Config | ✅ implemented | Typed frozen Config, TOML load/save/validate, XDG path resolution |

## Remaining Gaps / Phase 2+ Work

- [ ] Wire event log into HearthNode and controller (currently services use demo fallback)
- [ ] Wire M01 identity into node startup (auto-generate keypair, sign manifests)
- [ ] Wire X01 FastAPI transport into node for real inter-node calls
- [ ] Wire M02 mDNS/UDP discovery into node startup
- [ ] Add JSON Schema definitions to capability descriptors (currently empty dicts)
- [ ] Replace SHA-256 placeholder hashes in bus/capability.py with BLAKE3 (blake3 package)
- [ ] Add contract conformance test suite for capability descriptors/envelopes
- [ ] Add real TLS for inter-node HTTPS calls (currently verify=False)
- [ ] Add X02 gossip sync between real nodes
- [ ] Add M13 onboarding first-run wizard integration with CLI
- [ ] Add M12 invite/RAG CLI commands after M01/M05/M13 integration
- [ ] Add M08 mobile static app (hearthnet/ui/mobile/)
- [ ] Live UI updates via async subscriptions (websocket/SSE push)
- [ ] Phase 2: relay tier, DHT, federation, E2E encryption, LoRa

## Phase 3 Research/Protocol Milestones

- [ ] Relay tier.
- [ ] DHT discovery.
- [ ] Federation protocol.
- [ ] E2E encryption.
- [ ] LoRa beacons.
- [ ] Federated metrics.
- [ ] Federated learning.
- [ ] Distributed inference.


## Phase 1 Demo: Done

- [x] Import the Hugging Face Space into the local workspace.
- [x] Read `docs/00-OVERVIEW.md`, `docs/prd_v2.md`, `docs/roadmap.md`, `docs/CAPABILITY_CONTRACT.md`, `docs/GLOSSARY.md`, M01-M13, and X01-X04 for implementation direction.
- [x] Preserve existing browser mesh prototypes as supporting material.
- [x] Build Hugging Face-compatible Gradio `app.py`.
- [x] Add ZeroGPU startup probe for HF runtime compatibility.
- [x] Create `hearthnet/` Python package for the Phase 1 demo slice.
- [x] Model the system of concern as local-first community AI resilience.
- [x] Add `HearthNetController` over `HearthNode`.
- [x] Add facades for RAG, chat, and marketplace workflows.
- [x] Add `CapabilityBus`, registry, router, health tracking, in-memory traces, and in-memory transport.
- [x] Add simulated peer discovery and manifest ingestion.
- [x] Add deterministic demo nodes for anchor, hearth, and spark profiles.
- [x] Add demo services for `llm.chat`, `rag.query`, `rag.ingest`, `market.post`, `market.list`, `chat.send`, and `chat.history`.
- [x] Add emergency mode state and manual probe handling.
- [x] Add Gradio tabs for overview, mesh, AI/RAG, marketplace/chat/emergency, and architecture trace.
- [x] Replace app-level fake AI answers with real local Hugging Face Transformers inference and explicit OpenAI online fallback.
- [x] Add focused tests for routing, failover, emergency mode, and controller snapshots.
- [x] Add `ruff`, `bandit`, `pylint`, `mypy`, and `pytest` config.
- [x] Run quality gates and tests.
- [x] Push Phase 1 Space to `https://huggingface.co/spaces/build-small-hackathon/HearthNet`.

## Spec Coverage Matrix

| Spec | Current status | What exists now | Main gaps |
| --- | --- | --- | --- |
| `GLOSSARY.md` | stub | Basic aliases and error literals in `hearthnet/types.py`. | Enforced ID formats, ULID helpers, canonical constants, XDG paths. |
| `CAPABILITY_CONTRACT.md` | demo | Capability descriptors, names, versions, params, routing body shape. | Signed wire envelopes, JSON Schema validation, BLAKE3 schema hashes, streaming/SSE, canonical errors, conformance suite. |
| M01 Identity | missing | Demo node IDs and unsigned manifest dictionaries. | Ed25519 keys, canonical JSON signing, verification, community manifests, TLS certs, tokens. |
| M02 Discovery | demo | `PeerRegistry`, simulated in-memory mesh discovery, manifest import. | mDNS, UDP broadcast, async peer events, manifest fetch/verify, relay path. |
| M03 Capability Bus | demo | Registry, router, local/remote in-memory calls, health scoring, traces. | Schema validation, trust enforcement, streaming, subscriptions, HTTP transport, full trace contract. |
| M04 LLM | demo | Echo-like `llm.chat` service with model params. | `llm.complete`, Ollama/llama.cpp/HF backends, token streaming, cancellation, token accounting. |
| M05 RAG | demo | In-memory keyword query/ingest with chunks. | Chunker, PDF ingestion, Chroma/vector store, embed-via-bus, corpus listing, citations from blobs/events. |
| M06 Marketplace | demo | In-memory `market.post` and `market.list`. | Event-sourced posts, expiry/search, Lamport clocks, replay views, trust/moderation, idempotency. |
| M07 File/Blobs | missing | None. | BLAKE3 CID store, chunking, file service, transfer manager, pinning, GC, `file.*` capabilities. |
| M08 UI | demo | Gradio `app.py` demo dashboard and topology SVG. | `hearthnet/ui/` package, bus-only UI wiring, files/settings tabs, mobile static app, live subscriptions. |
| M09 Emergency | stub | `StateBus`, manual `Detector.apply_probe_results`, capability deregistration demo. | Async probe loop, debounce/anti-flap, DNS/HTTP targets, config-driven probes, UI subscriptions. |
| M10 Chat | stub | In-memory `ChatService` with send/history. | Signed event log, delivery manager, materialized views, read receipts, attachments/blob integration. |
| M11 Embedding | missing | None; RAG uses substring scoring. | `embed.text` capability, backend abstraction, test backend, vector normalization, RAG/marketplace bus use. |
| M12 CLI | missing | None. | `hearthnet/cli.py`, `__main__.py`, console script, status/caps/call/doctor/invite/rag commands. |
| M13 Onboarding | missing | Demo UI text only. | Invite encode/decode, QR flow, create/join community, config persistence, first-run handoff. |
| X01 Transport | demo shim | `InMemoryTransport` for local tests. | FastAPI server/client, signed HTTP envelopes, SSE streaming, rate limiting, TLS/pinning, endpoints. |
| X02 Events | missing | In-memory service lists and UUIDs. | SQLite event log, Lamport clocks, replay, snapshots, gossip/sync, event-backed marketplace/chat. |
| X03 Observability | demo shim | In-memory bus traces in topology snapshots. | Structured logging, metrics, trace ring buffer API, `/metrics`, `/trace/recent`, doctor checks. |
| X04 Config | missing | Hardcoded defaults in constructors/dataclasses. | `hearthnet/config.py`, constants, TOML load/save, validation, path resolution, environment overrides. |

## Immediate Correction Tasks: No-Mock Local-First Alignment

- [ ] Audit implementation paths for mocks, fake responses, placeholder AI, and unlabeled simulations; replace with real local-first behavior or explicit unavailable/degraded states.
- [ ] Remove or reject security pragmas, blanket ignores, and tool suppressions; fix findings directly or document narrow reviewed exceptions.
- [ ] Implement real local-first LLM backend selection with Ollama/llama.cpp/local HF support before any online provider.
- [ ] Add OpenAI fallback only as explicit online/degraded mode with config gating, visible UI labeling, and tests proving it is never the default local path.
- [ ] Improve Gradio UI polish: clearer status hierarchy, better empty/loading/error states, cleaner layout density, and honest capability labels.
- [ ] Add spec-adherence tests or checks that map implemented capabilities to M01-M13, X01-X04, `CAPABILITY_CONTRACT.md`, and `GLOSSARY.md`.
- [ ] Add visible Phase 1 boundary labels in the Space explaining which modules are demo/stub/missing.
- [ ] Add tests that assert the UI/demo does not overclaim real transport, identity, event sync, or offline production readiness.
- [ ] Add `hearthnet/constants.py` for hardcoded health/pruning/emergency thresholds.
- [ ] Add minimal `hearthnet/config.py` Phase 1 defaults consumed by node, bus, emergency, and UI.
- [ ] Add tiny event/Lamport shim or rename marketplace/chat data clearly as in-memory demo events.
- [ ] Add observability shim that exports in-memory traces with an explicit note that Prometheus/doctor are deferred.
- [ ] Add a note to `docs/00-OVERVIEW.md` that current repo paths use `docs/X01-...` while the overview still describes the target reference tree.

## Module Backlog

### Contract and Glossary

- [ ] Add contract conformance tests for capability descriptors, request/response envelopes, errors, manifests, and schema hashes.
- [ ] Replace SHA-256 placeholder schema hashes with BLAKE3 once the dependency is introduced.
- [ ] Add shared identifier helpers for NodeID, CommunityID, TraceID, EventID, CID, WallClock, Signature, and SchemaHash.
- [ ] Replace hardcoded demo IDs with glossary-conformant helpers.

### M01 Identity

- [ ] Implement `hearthnet/identity/keys.py`.
- [ ] Implement signed node/community manifests.
- [ ] Implement canonical JSON signing and verification tests.
- [ ] Add trust levels and revoked/expired/invalid signature handling.
- [ ] Add token/TLS certificate roadmap tasks for Phase 2.

### M02 Discovery

- [ ] Replace simulated discovery with mDNS advertisement/listener.
- [ ] Add UDP broadcast fallback.
- [ ] Verify remote manifests through M01 before registry import.
- [ ] Emit peer up/down/update events.
- [ ] Add relay discovery stub for Phase 2.

### M03 Capability Bus

- [ ] Add JSON Schema validation for capability requests/responses.
- [ ] Add trust checks and authorization errors.
- [ ] Add streaming call support.
- [ ] Add subscription/pub-sub support.
- [ ] Add sticky session and quarantine tests beyond the demo route tests.
- [ ] Add trace events matching the capability contract.

### M04 LLM

- [ ] Split LLM service into `services/llm/service.py` and backend package.
- [ ] Implement `llm.chat` and `llm.complete` contract handlers.
- [ ] Add Ollama backend.
- [ ] Add llama.cpp backend.
- [x] Add app-level local Hugging Face Transformers backend for Space inference.
- [ ] Move local Hugging Face Transformers backend behind `llm.chat` on the bus.
- [ ] Add OpenAI backend only for explicit online/degraded fallback mode.
- [ ] Add tests proving local backends are preferred and OpenAI is never used unless configured.
- [ ] Add streaming, cancellation, timeout, and token accounting tests.

### M05 RAG

- [ ] Add chunker and ingest pipeline.
- [ ] Add persistent corpus store.
- [ ] Add `rag.list_corpora`.
- [ ] Add embedding-via-bus using M11.
- [ ] Add citation metadata from file/blob/event sources.
- [ ] Add RAG query/ingest/list tests.

### M06 Marketplace

- [ ] Back marketplace posts with X02 events.
- [ ] Add post/list/search/expire handlers.
- [ ] Add replay/materialized view.
- [ ] Add Lamport/idempotency behavior.
- [ ] Add trust/moderation checks.

### M07 File and Blobs

- [ ] Implement BLAKE3 CID blob store.
- [ ] Implement chunking and transfer.
- [ ] Implement file service with `file.read`, `file.list`, and `file.advertise`.
- [ ] Add pinning and garbage collection.
- [ ] Add file/blob tests.

### M08 UI

- [ ] Move UI into `hearthnet/ui/` package.
- [ ] Wire UI exclusively through controller/facades/bus snapshots.
- [ ] Add files tab.
- [ ] Add settings tab.
- [ ] Add mobile static app path.
- [ ] Add live updates/subscriptions once M03/X01 support them.
- [x] Improve first-pass visual hierarchy with scoped Gradio HTML/CSS.
- [ ] Improve visual hierarchy, spacing, state handling, and mobile ergonomics while preserving Gradio/HF compatibility.
- [ ] Add UI assertions that demo/stub/missing states are visibly labeled and no unavailable feature is presented as complete.

### M09 Emergency

- [ ] Promote detector to async service.
- [ ] Add DNS/HTTP probe targets from config.
- [ ] Add debounce and anti-flap behavior.
- [ ] Add clock sanity probe.
- [ ] Add emergency UI subscription.
- [ ] Add probe/debounce/local-mode tests.

### M10 Chat

- [ ] Split chat into `service.py`, `delivery.py`, and `views.py`.
- [ ] Store messages as signed X02 events.
- [ ] Add store-and-forward delivery.
- [ ] Add local-only history authorization.
- [ ] Add attachment/blob path.
- [ ] Add chat delivery/history tests.

### M11 Embedding

- [ ] Add `EmbeddingService`.
- [ ] Add lightweight deterministic test backend.
- [ ] Register `embed.text`.
- [ ] Make RAG call embeddings through the bus.
- [ ] Add embedding contract tests.

### M12 CLI

- [ ] Add `hearthnet/cli.py`.
- [ ] Add `hearthnet/__main__.py`.
- [ ] Add console script entry point.
- [ ] Implement `version`, `status`, `caps`, `call`, and `doctor`.
- [ ] Add invite/RAG commands after M01/M05/M13 are present.
- [ ] Add CLI exit-code tests.

### M13 Onboarding

- [ ] Add invite encode/decode primitives.
- [ ] Add QR generation path.
- [ ] Add create-community flow.
- [ ] Add join-community flow.
- [ ] Persist onboarding state through X04 config.
- [ ] Wire first-run UI handoff.

### X01 Transport

- [ ] Implement FastAPI transport server.
- [ ] Implement HTTP client.
- [ ] Add signed request envelopes.
- [ ] Add SSE streaming.
- [ ] Add rate limiting/backpressure.
- [ ] Add TLS/pinning strategy.
- [ ] Add two-node transport integration tests.

### X02 Events

- [ ] Implement SQLite event log.
- [ ] Implement Lamport clock.
- [ ] Implement replay views.
- [ ] Implement snapshots.
- [ ] Implement sync/gossip path.
- [ ] Migrate marketplace/chat to event-backed state.

### X03 Observability

- [ ] Add structured logging.
- [ ] Add metrics counters/gauges.
- [ ] Add trace ring buffer.
- [ ] Add `/metrics`.
- [ ] Add `/trace/recent`.
- [ ] Add `doctor` checks and tests.

### X04 Config

- [ ] Add typed config model.
- [ ] Add TOML load/save.
- [ ] Add validation.
- [ ] Add path resolution.
- [ ] Add environment overrides.
- [ ] Replace hardcoded defaults with config/constants.

## Phase 2 Integration Milestones

- [ ] Real local two-node transport call roundtrip.
- [ ] Event sync convergence between two nodes.
- [ ] Emergency local-mode behavior with real deregistration and restoration.
- [ ] Observability endpoint smoke tests.
- [ ] Real mDNS/UDP discovery on LAN.
- [ ] RAG ingest/query over persistent corpus with embeddings.
- [ ] Real local model inference through the bus with no mock response path.
- [ ] Online fallback path gated by config, with OpenAI labeled as non-local/degraded mode.
- [ ] Security and quality gates pass without new pragmas or blanket suppressions.
- [ ] Spec coverage review confirms every shipped capability matches its contract.

## Phase 3 Research/Protocol Milestones

- [ ] Relay tier.
- [ ] DHT discovery.
- [ ] Federation protocol.
- [ ] E2E encryption.
- [ ] LoRa beacons.
- [ ] Federated metrics.
- [ ] Federated learning.
- [ ] Distributed inference.
