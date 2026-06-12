# HearthNet — Task Tracker

## Status Summary (June 2026)

All Phase 1 (M01-M13, X01-X04), Phase 2 (M14-M25, X05-X07), and Phase 3 experimental
(M26-M31) modules are implemented. **489 tests pass, 59 skipped (E2E), 0 fail**.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full module map, data flows, and local-to-HF setup guide.
See [docs/IMPROVEMENTS.md](docs/IMPROVEMENTS.md) for the full improvement backlog and prize targeting analysis.

---

## Security Audit & Fixes (June 12)

**Full assessment:** [SECURITY_AUDIT_ASSESSMENT.md](SECURITY_AUDIT_ASSESSMENT.md)

**Critical Vulnerabilities Fixed:**
- ✅ **CVE-2025-3000 (PyTorch)**: Updated `torch>=2.3.0` → `torch>=2.12.1` to patch memory corruption in torch.jit.script
- ✅ **CVE-2025-71176 (pytest)**: Updated `pytest>=8.2` → `pytest>=8.5.0` to patch /tmp race condition on UNIX
- ✅ **RCE via trust_remote_code=True** (florence2.py:52-58): Added hardcoded allowlist of approved Microsoft models, added validation in __init__ to prevent loading arbitrary model IDs with trust_remote_code

**High Priority Issues Documented:**
- **Sync HTTP in async context** (peering.py:208, 230): Intentional — PeeringClient methods are synchronous-only by design. If called from async, wrap with asyncio.to_thread(). Documented in class docstring + SECURITY_AUDIT_ASSESSMENT.md
- **System prompt secrets** (app_nemotron.py:169): False positive — no actual secrets in system prompts, only instructions

**False Positives Excluded:**
- agent-audit (43 findings): No .agent.md files in HearthNet; tool not applicable to capability-bus architecture
- Semgrep system-prompt-contains-secret: Regex noise match, no real secrets present

**Dependencies Updated:**
- requirements.txt: torch>=2.12.1
- requirements-dev.txt: pytest>=8.5.0

**Related files:**
- [SECURITY_AUDIT_ASSESSMENT.md](SECURITY_AUDIT_ASSESSMENT.md) — full vulnerability analysis + triage table
- [hearthnet/services/image/backends/florence2.py](hearthnet/services/image/backends/florence2.py) — allowlist + validation
- [hearthnet/federation/peering.py](hearthnet/federation/peering.py) — security note on sync HTTP

---

**Hackathon additions (June 11):**

- `app_nemotron.py`: Second Gradio Space — Nemotron Document Intelligence
  (structured extraction, Q&A, summarisation, push-to-mesh RAG)
  Targets: NVIDIA RTX 5080 + Off Brand badge
- `hearthnet/ui/tabs/nemotron.py`: Nemotron tab for embedding in main app
- `hearthnet/services/llm/backends/modal_backend.py`: Modal serverless GPU backend
  (targets Modal Best Use $10k credits)
- `scripts/modal_deploy.py`: One-command Modal deployment script
- `hearthnet/node.py install_services()`: now auto-discovers Nemotron (NVIDIA_API_KEY),
  MiniCPM (MINICPM_URL), and Modal (MODAL_ENDPOINT) backends from env vars
- README: added `nemotron`, `minicpm`, `modal` tags; expanded hackathon section
  with sponsor prize targeting table
- `docs/IMPROVEMENTS.md`: comprehensive improvement backlog with GPT-4o rating,
  29 improvement items, and priority matrix

**README + submission (June 11):**
- Full README rewrite: YAML tags, screenshots, author links, architecture, module ref
- Tags: backyard-ai, tiny-titan, best-agent, nemotron, minicpm, modal
- Links: HF Chris4K, X @zX14_7, GitHub ckal
- Placeholders: demo video + social post (needed before June 15)

**Previous fixes (June 11):**
- NameError: node_id in settings.py f-string — fixed to literal string
- TestTabBuildRegression (6 tests) — catches build-time NameError before HF deploy
- TestUS11ApiCoverage + TestUS12MeshConnection (8 new tests)

**Recent fixes (June 10 — Phase 3 wiring):**
- MoeService: moe.route / moe.register / moe.list / moe.handoff registered on bus (M27)
- ModelDistributionService: now always registered (auto-creates ~/.hearthnet/blobs if no blob_store passed) (M26)
- PlantIdentificationService: tool.plant_identify on bus — local Florence-2 → HF API → unavailable (M21)
- PLANT_TOOL_DEFINITION: ready for ToolExecutor (LLM can call plant_identify mid-generation)
- Getting Started tab: documents pip install, MoE routing, BitTorrent model sharing, plant tool
- README: updated test count, pip install, M26/M27 status to "registered"

**Previous fixes (June 10):**
- FileService: real file.put / file.get / file.list / file.delete via bus (BLAKE3 CID)
- Real RagService used in production (no longer importing demo stub)
- Chat tab: missing return fixed (was silently failing on exceptions)
- Emergency probe button: now actually runs DNS+HTTP probes and shows results
- QR invite: graceful fallback when PyNaCl/community manifest not available
- 10-document seed RAG corpus in HF Space (emergency, first aid, mesh, setup)
- Marketplace: market.delete capability added
- Test isolation: nest_asyncio.apply() in conftest.py fixes Python 3.13 + pytest-asyncio 0.26

**impl_ref §22 gap-fill (June 11):**
- 9 CLI commands added: log, erase, rag list/ingest/reindex, invite create/redeem, version
- ManifestPublisher + PeriodicTask in node.py
- LmStudioBackend, HfApiBackend, AnthropicApiBackend (M04)
- CommunityPolicy, CommunityMember, RevokedEntry in identity/manifest.py (M01)
- hearthnet_theme + emergency_theme in ui/theme.py (M08)
- TopologyComponent with push_trace/push_topology/render in ui/topology.py (M08)
- FlowControl, RateCheck, RateLimiter in transport/backpressure.py (X01)
- Frame + SseReader in transport/streams.py (X01)
- DiscoveryError in discovery/__init__.py (M02)
- RegistryEvent in bus/registry.py (M03)
- CheckResult alias + TrackioExporter + detach() in observability/ (X03)
- build_onboarding alias in ui/onboarding.py (M13)
- Phase 3 type aliases in types.py (ShardID, ExpertID, ClaimID, AlertID, etc.)
- Phase 3 constants in constants.py (all M26-M31, X08, X09 constants)
- ARCHITECTURE.md created
- scripts/connect_to_hf.py — script to peer local node with HF Space

**Pending / future work:**
- pip install hearthnet — not yet published to PyPI (use pip install -e . from repo)
- Custom UI (non-Gradio, modern HTML/CSS) — planned as second UI alongside current reference
- Modal/LoRA fine-tuning integration — future M28 fedlearn
- ShardServer.forward() — PipelineOrchestrator.run() — real torch sharding (M26 placeholder)

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
- [x] pytest — 133 passed, 51 skipped (E2E), 0 failed

---

## Test Suites

| File | Tests | Coverage |
|------|-------|----------|
| tests/test_phase1_routing.py | 8 | Bus routing, failover, capabilities |
| tests/test_phase1_emergency_snapshot.py | 5 | Emergency mode, controller snapshot |
| tests/test_phase2_modules.py | 23 | M14-M25, X05-X07 |
| tests/test_phase3_experimental.py | 15 | M26-M31, ResearchConfig |
| tests/test_wiring.py | 22 | Wiring integration: X01/X02/X06/X09/M02/M22 |
| tests/test_e2e_user_stories.py | 60 | Gradio UI E2E (real browser, Playwright) |

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

- [ ] Wire real event log (X02) into HearthNode on startup (services still use in-memory fallback)
- [ ] Wire X01 FastAPI transport into node.start() for real inter-node HTTP calls
- [ ] Wire M02 mDNS/UDP discovery into node.start() (PeerRegistry not yet auto-started)
- [ ] ShardServer.forward() / PipelineOrchestrator.run() — real torch sharding (M26 needs torch)
- [ ] Gossip sync (X02 SyncClient/SyncServer) between live nodes in production
- [ ] Live UI push via WebSocket pubsub (X06 wired into StateBus; Gradio event loop integration pending)
- [ ] M22 Flutter mobile app — separate repo; Python anchor-side helpers done
- [ ] Second implementation of M32 protocol (conformance is performative without a second impl)
- [ ] pip install hearthnet — not yet published to PyPI

- [] change model (ask user), deploy to modal , cohere , check all tags from 29 wins , demo video, poss links ...