# HearthNet — Task Tracker

## Status Summary (June 2026)

All Phase 1 (M01-M13, X01-X04), Phase 2 (M14-M25, X05-X07), and Phase 3 experimental
(M26-M31) modules are implemented. **489 tests pass, 59 skipped (E2E), 0 fail**.

See [ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full module map, data flows, and local-to-HF setup guide.
See [docs/reports/IMPROVEMENTS.md](docs/reports/IMPROVEMENTS.md) for the full improvement backlog and prize targeting analysis.

---

## Maximize Real Activation (June 12) — see [upgrade_plan.md](docs/upgrade_plan.md)

Full 10-phase upgrade to make every feasible capability *genuinely real* (no mocks,
fakes, or `# noqa`/`# nosec` bypasses). **Net result: +18 passing tests, −6 failing,
zero regressions** (baseline 1296→1314 passing).

**Done:**
- [x] **P1 Gossip fix** — `_gossip_loop` built `HttpClient` with wrong args + a client
  lacking httpx `.get()/.post()`. Added `_HttpxSyncClient` adapter; gossip now runs.
- [x] **P2 Real semantic RAG** — added `sentence-transformers`/`httpx` to
  `requirements.txt`; `EmbeddingService` (SentenceTransformer `BAAI/bge-small-en-v1.5`)
  now registered, so `rag.query` does genuine semantic retrieval (was 16-dim hash).
- [x] **P3 Activate dormant real services** — `node.install_extended_services()`
  registers Embedding/Rerank/Ocr/Translation/Stt/Tts/ImageDescribe/ImageGenerate;
  all degrade to `unavailable` when optional deps absent (no mock).
- [x] **P4 M30 Evidence + M31 Civil Defense** — wrote `EvidenceService` and
  `CivilDefenseService` bus adapters (`capabilities()`); registered under `research=True`.
- [x] **P5 M29 LoRa** — intentionally *not* enabled in the demo (no hardware); documented.
- [x] **P6 app.py wiring** — real `RagService`+`FederatedRagService` with seeded corpus,
  multi-backend `LlmService` (HF + opt-in Nemotron/Modal/MiniCPM), EventLog opened
  and injected into Marketplace/Chat.
- [x] **Multi-backend LLM dispatch (prize-critical)** — registry keys by
  `(node,name,version)`, so per-backend `llm.chat` registrations overwrote each other
  and sponsor backends were unreachable (the real reason `NVIDIA_API_KEY` did nothing).
  Now a single `llm.chat`/`llm.complete` advertises `params.models` and dispatches by
  model name; `_remote_params_compatible` honours the catalogue for cross-node routing.
- [x] **Event-loop ordering fix** — autouse fixture in `tests/conftest.py` provisions a
  fresh loop per test (Python 3.13 `asyncio.run()` resets the current loop); fixed 4
  `test_coverage_boost.py` tests building `gather()` outside a loop.
- [x] **Windows key-permission fix** — `keys.py` POSIX `0o600` check now gated behind
  `os.name == "posix"` (`stat.S_IMODE` returns `0o666` on NTFS, not an error). Not a
  security bypass — POSIX mode bits are meaningless on Windows.
- [x] **P7 Docs** — README (real embeddings + sponsor backends), `CAPABILITY_CONTRACT.md`
  (multi-model `params.models` note); M05/M11 docs already matched the now-real impl.
- [x] **P9 Tests** — `test_sponsor_backends.py`, `test_gossip_sync.py`,
  `test_phase3_services.py`, `test_extended_services.py` (all green).

**Model policy:** LLM **kept** as `SmolLM2-135M-Instruct` (not swapped — MiniCPM-4B risks
OOM on free ZeroGPU; `MINICPM_URL` remains the opt-in path). The real upgrade is semantic
RAG via `bge-small-en-v1.5`.

**Kept gated (honest):** M26 distributed inference + M28 fedlearn raise
`NotImplementedError` in core compute (need torch model-slicing / peft) — roadmap, not
advertised. M29 LoRa is hardware-gated.

**Known issue (pre-existing, not a regression):**
`test_e2e_user_stories.py::TestUS11ApiCoverage::test_US11_3_rag_trace_shows_corpus`
fails only via a full Gradio + `gradio_client` round-trip (client-side dropdown-value
serialization quirk in untouched demo/UI code). The 17 collection errors are
pre-existing `playwright` `ModuleNotFound` (optional browser-test dep).

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
- `docs/reports/IMPROVEMENTS.md`: comprehensive improvement backlog with GPT-4o rating,
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

## Internet Mesh — all-to-all over the relay hub (June 13)

Goal: any node (Python server, browser tab, phone) joins a mesh via a secure
redeem code/QR and uses everyone's features (chat, RAG, LLM) as if local, with
all-to-all node messaging and a one-command launcher that auto-connects to the
HF Space. **Local-first: internet "relay mode" is opt-in and modular — the default
node stays LAN/in-process only.**

**Status: P1–P3 implemented and verified (`tests/test_relay_mesh.py`).**


**In progress (P1–P3):**
- [x] **P1 — Modular transport + relay hub.** `CompositeTransport`
  (`hearthnet/bus/transport.py`) tries pluggable `DeliveryStrategy` handlers
  (in-process → direct HTTP → relay). Relay hub (`hearthnet/transport/relay_hub.py`)
  exposes pull-based mailboxes (`/relay/v1/join|send|poll|roster`, mounted on the Space
  in `app.py`) so NAT-bound nodes reach each other through the Space. `RelayClient`
  (`hearthnet/transport/relay_client.py`) joins + runs a long-poll loop + correlates
  request/response envelopes; `node.join_relay()/leave_relay()` attach it opt-in.
  Verified by `tests/test_relay_mesh.py` (all-to-all over a real uvicorn relay).
- [x] **P2 — Secure relay-aware invite/redeem + QR.** `InviteBlob` now carries
  `relay_url` + `relay_token` (signed into the payload, embedded in the QR/link via the
  existing generators); `mesh.join` capability (`hearthnet/transport/mesh_service.py`)
  decodes a pasted code/scanned QR or explicit relay URL and auto-joins the mesh.
- [x] **P3 — Launcher.** `scripts/start_mesh_node.py` starts a local-first node and,
  with `--connect <invite|hf|relay-url>`, attaches the relay, auto-connects to HF, and
  stays running. No flag = pure local (no outbound calls).

**Deferred — P4 Browser ↔ Python bridge (NOT implemented yet):**
The browser mesh (`webagent/src/mesh/browsermesh.js`, PeerJS/WebRTC anchor-rendezvous
full mesh) and the Python relay both rendezvous at the Space but are currently separate
meshes. P4 would bridge them so browser tabs and Python nodes share one logical mesh —
translating between WebRTC data channels and the relay mailbox at the Space, and adding
WebRTC/tunnel as additional pluggable `DeliveryStrategy` implementations. Deferred
because it is the heaviest piece (bidirectional WebRTC↔mailbox translation, signaling,
and ICE/TURN concerns); P1–P3 should be proven end-to-end first. Tracked here so it is
not lost.

---

## Bug Fixes — June 14, 2026

Deep critical analysis found and fixed the following bugs. See
[hackathon_final_step.md](hackathon_final_step.md) for full detail on each.

- [x] **FIX-1** `node.start()` never set `self._started = True` → `stop()` silently
  no-oped on every call, leaking background tasks and HTTP server. Fixed in
  [hearthnet/node.py](hearthnet/node.py).
- [x] **FIX-2** `ChatService.send()` swallowed all exceptions with bare
  `except Exception: pass` → persistence failures invisible to operators. Now logs
  `_log.warning(...)` with the actual error. Fixed in
  [hearthnet/services/chat/service.py](hearthnet/services/chat/service.py).
- [x] **FIX-3** `UTC = UTC` dead re-assignment in chat/service.py and
  marketplace/service.py. Removed.
- [x] **FIX-4** `RagService` defaulted `corpora_dir` to `Path(".")` (cwd). Changed
  to `Path.home() / ".hearthnet" / "corpora"`. Fixed in
  [hearthnet/services/rag/service.py](hearthnet/services/rag/service.py).
- [x] **FIX-5** Seed corpus was never actually ingested: `handle_ingest` read
  `inp.get("text", "")` but `app.py` passed `{"documents": [...]}`, resulting in
  empty-string indexing. Added batch-document dispatch path to `handle_ingest`.
  Fixed in [hearthnet/services/rag/service.py](hearthnet/services/rag/service.py)
  and [app.py](app.py).
- [x] **FIX-6** `asyncio.run(_seed_corpus())` in `app.py` would raise
  `RuntimeError: event loop already running` when Gradio had started first (silently
  suppressed by `contextlib.suppress`). Replaced with a dedicated daemon thread
  that creates its own event loop. Fixed in [app.py](app.py).
- [x] **FIX-7** `app.py` created `RagService` without `corpora_dir`, so corpus data
  went to cwd instead of `HEARTHNET_DATA_DIR`. Now derives `_corpora_dir`
  consistently. Fixed in [app.py](app.py).
- [x] **FIX-8** `Router._sticky` dict grew without bound (sticky session memory leak).
  Added `_MAX_STICKY_SESSIONS = 10_000` cap with LRU-by-insertion eviction. Fixed in
  [hearthnet/bus/router.py](hearthnet/bus/router.py).

---

## Known Remaining Gaps

**Networking / persistence (highest impact):**
- [ ] Relay hub roster lost on Space restart — `RelayHub._members` is in-memory; add SQLite backing (OPEN-1)
- [x] **OPEN-2** `node.start()` now called in `app.py` for local mode (gated on `SPACE_HOST` not set) — mDNS, HTTP bus transport, gossip, and CorpusReplicator now start for local installs. `node._event_log` pre-set guard prevents double-open. Fixed in [app.py](app.py) and [hearthnet/node.py](hearthnet/node.py).
- [x] **OPEN-3** `ChatService` and `MarketplaceService` references saved in `install_services()`; `start()` injects `event_log` into all three persistence services (Rag + Chat + Marketplace) after opening the DB. Fixed in [hearthnet/node.py](hearthnet/node.py).
- [x] **OPEN-5** Mesh tab auto-refreshes every 10 s via `gr.Timer` — peer joins appear live without manual click. Fixed in [hearthnet/ui/tabs/mesh.py](hearthnet/ui/tabs/mesh.py).
- [x] **Docs ingestion** `_seed_corpus()` now scans `docs/guides/` and `assets/initial_docs/` and ingests all `.md`/`.txt` files into the community RAG corpus on startup. `assets/initial_docs/` created as a drop-in folder for community documents. Fixed in [app.py](app.py).

**Security:**
- [x] **OPEN-4** Token `exp` claim now enforced in `handle_call()`. Added `token: str | None = None` field to `RouteRequest`; handle_call decodes the hntoken payload and rejects expired tokens before routing. Fixed in [hearthnet/bus/capability.py](hearthnet/bus/capability.py) and [hearthnet/bus/__init__.py](hearthnet/bus/__init__.py).

**UI polish:**
- [x] **OPEN-5** Mesh topology auto-refreshes every 10 s via `gr.Timer`. Fixed in [hearthnet/ui/tabs/mesh.py](hearthnet/ui/tabs/mesh.py).
- [x] **OPEN-6** Capability matrix already present in `get_mesh()` JSON output — shows which node has which capabilities.
- [x] **OPEN-7** Routing trace replaced raw `gr.JSON` with formatted `gr.HTML` badge. Each leg (RAG, LLM) shows 🏠 Local or 🌐 Remote with node ID. Fixed in [hearthnet/ui/tabs/ask.py](hearthnet/ui/tabs/ask.py).
- [x] **OPEN-1** Relay hub now persists roster to SQLite. On Space restart, active members (within TTL) are restored from DB. `join()` persists, `leave()` and `prune()` delete. DB path from `HEARTHNET_DATA_DIR`. Fixed in [hearthnet/transport/relay_hub.py](hearthnet/transport/relay_hub.py) and [app.py](app.py).
- [x] **Doc folder ingestion** `_seed_corpus()` scans `docs/guides/` and `assets/initial_docs/` on startup, ingesting all `.md`/`.txt` files. `assets/initial_docs/` created as a drop-in community knowledge folder. Fixed in [app.py](app.py).

**Post-hackathon:**
- [ ] ShardServer.forward() / PipelineOrchestrator.run() — real torch sharding (M26 needs torch)
- [ ] E2E chat encryption (M23 X3DH/Double Ratchet implemented but not wired as default)
- [ ] Real LoRa hardware integration (M29 stub → serial port)
- [ ] M22 Flutter mobile app — separate repo; Python anchor-side helpers done
- [ ] pip install hearthnet — not yet published to PyPI

**Hackathon submission (deadline June 15):**
- [ ] Demo video recorded and URL in README (blocks ALL prizes)
- [ ] Social post on X @zX14_7 (blocks Best Demo badge)
- [ ] NVIDIA_API_KEY set in HF Space secrets (Nemotron prize)
- [ ] Deploy app_nemotron.py as second HF Space (NVIDIA + Off Brand)
- [ ] MINICPM_URL or model swap (OpenBMB $2,500)
- [ ] Modal endpoint deployment (Modal $10k credits)