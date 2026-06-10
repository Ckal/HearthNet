# HearthNet — Task Tracker

## Status Summary (June 2026)

All Phase 1 (M01-M13, X01-X04), Phase 2 (M14-M25, X05-X07), and Phase 3 experimental
(M26-M31) modules are implemented. **102 tests pass, 0 fail** (unit + integration + E2E).

**Recent fixes (June 10):**
- FileService: real file.put / file.get / file.list / file.delete via bus (BLAKE3 CID)
- Real RagService used in production (no longer importing demo stub)
- Chat tab: missing return fixed (was silently failing on exceptions)
- Emergency probe button: now actually runs DNS+HTTP probes and shows results
- QR invite: graceful fallback when PyNaCl/community manifest not available
- 10-document seed RAG corpus in HF Space (emergency, first aid, mesh, setup)
- Marketplace: market.delete capability added
- Test isolation: nest_asyncio.apply() in conftest.py fixes Python 3.13 + pytest-asyncio 0.26

**Pending / future work:**
- pip install hearthnet — package is defined in pyproject.toml; not yet published to PyPI
- Custom UI (non-Gradio, modern HTML/CSS) — planned as second UI alongside current reference
- Modal/LoRA fine-tuning integration — future M28 fedlearn
- External tool integration (plant_identification_tool pattern) — future M21 tool calls

---

## Phase 1 — Complete

- [x] M01 Identity (Ed25519, canonical JSON, node/community manifests)
- [x] M02 Discovery (mDNS, UDP broadcast, PeerRegistry with async events)
- [x] M03 Capability bus (schema validation, router, health, traces)
- [x] M04 LLM (Ollama, llama.cpp, HF Transformers backends; OpenAI online fallback)
- [x] M05 RAG (chunker, ChromaDB + in-memory, IngestPipeline, bus embed)
- [x] M06 Marketplace (event-sourced, post/list/expire/search)
- [x] M07 File blobs (BLAKE3 CID store, chunking, TransferManager)
- [x] M08 UI (Gradio, 6 tabs: Ask/Chat/Marketplace/Files/Emergency/Settings)
- [x] M09 Emergency (async probe loop, DNS+HTTP, anti-flap, StateBus)
- [x] M10 Chat (event-sourced, ChatView, DeliveryManager)
- [x] M11 Embedding (embed.text, SimpleHashBackend, SentenceTransformerBackend)
- [x] M12 CLI (click, ask/node info/caps/call/doctor/trace)
- [x] M13 Onboarding (InviteBlob, QR, create/join/redeem community)
- [x] X01 Transport (FastAPI server 12 endpoints, HttpClient, SSE, TLS)
- [x] X02 Events (SQLite WAL, LamportClock, ReplayEngine, MaterialisedView, SnapshotStore)
- [x] X03 Observability (structured JSON logging, prometheus metrics optional, trace ring buffer)
- [x] X04 Config (typed frozen Config, TOML load/save, XDG paths, env overlay)

---

## Phase 2 — Complete

- [x] M14 Federation (FederationManifest, bilateral peering, FederationService)
- [x] M15 Relay tier (RelayClient, NAT traversal, keepalive, push token registry)
- [x] M16 Capability tokens (hntoken://v1/ Ed25519 JWS-style, AuthService)
- [x] M17 OCR (Tesseract + TrOCR backends, image/pdf capabilities)
- [x] M18 Translation (NLLB backend, LRU cache, 4000-char limit)
- [x] M19 STT/TTS (WhisperBackend local STT, EdgeTtsBackend synthesis)
- [x] M20 Vision (Florence-2 image describe, generate placeholder)
- [x] M21 Tool calls (ToolDefinition, ToolCall, ToolResult, ToolExecutor, run_loop)
- [x] M22 Mobile native (MobileInviteBlob, hnapp:// deep links, MobilePushService)
- [x] M23 E2E encryption (X3DH, Double Ratchet fixed bug, envelope, prekeys)
- [x] M24 Reranking (BGE + CrossEncoder, 100-doc limit, bus integration)
- [x] M25 Group chat (ThreadService, ThreadViewStore, event-sourced)
- [x] X05 DHT (Kademlia, 256-bucket routing table, KademliaNode, bootstrap)
- [x] X06 WebSocket (WebSocketSession, WebSocketClient, WebsocketPubSub)
- [x] X07 Federated metrics (NodeMetricsTick, MetricsAggregator, OTLP export)

---

## Phase 3 — Experimental Stubs (feature-flag gated)

All enabled via config.research.* flags (all default False).

- [x] M26 Distributed inference (ShardDescriptor, Pipeline, PipelineOrchestrator)
- [x] M27 MoE routing (ExpertDescriptor, ExpertRegistry, MoeRouter)
- [x] M28 Federated learning (FedLearnCoordinator, RoundManifest)
- [x] M29 LoRa beacons (32-byte frame encoding, LoraBeaconService)
- [x] M30 Evidence graph (Claim, ClaimStore, Attestation, Dispute; EBKH import)
- [x] M31 Civil defense NRW (Alert, RoleCertificate, AuditChain, CivilDefenseService)

---

## Quality Gates — All Passing

- [x] ruff — no lint errors
- [x] bandit — 0 HIGH findings, intentional nosec items documented
- [x] mypy — passes (optional deps handled with TYPE_CHECKING guards)
- [x] pylint — no blocking issues
- [x] pytest — 62/62 pass (51 unit + 11 E2E Playwright)

---

## Test Suites

| File | Tests | Coverage |
|------|-------|----------|
| tests/test_phase1_routing.py | 8 | Bus routing, failover, capabilities |
| tests/test_phase1_emergency_snapshot.py | 5 | Emergency mode, controller snapshot |
| tests/test_phase2_modules.py | 23 | M14-M25, X05-X07 |
| tests/test_phase3_experimental.py | 15 | M26-M31, ResearchConfig |
| tests/test_e2e_playwright.py | 11 | Gradio UI E2E (real browser, Playwright) |

---

## Architecture Notes

- All services implement health() -> dict returning {"status": "ok" | "unavailable"}
- All service handlers receive RouteRequest(capability, version_req, body, caller, trace_id)
- Response format: {"output": {...}, "meta": {}}
- No mocks in implementation paths; heavy optional deps fail gracefully
- OpenAI only as opt-in online fallback — never the default local path
- No security-tool suppression pragmas except narrow reviewed nosec comments

---

## Known Remaining Gaps

- [ ] Wire real event log (X02) into HearthNode on startup (services still use demo/fallback)
- [ ] Wire X01 FastAPI transport into node for real inter-node HTTP calls
- [ ] Wire M02 mDNS/UDP discovery into node startup
- [ ] M22 Flutter mobile app (separate repo; Python anchor-side helpers are done)
- [ ] Contract conformance suite against CAPABILITY_CONTRACT.md (X09 spec)
- [ ] Gossip sync (X02 SyncClient/Server) between live nodes
- [ ] Live UI push updates via WebSocket (X06 pubsub wired into UI)
- [ ] Add M08 mobile static app helpers (hearthnet/ui/mobile/)
