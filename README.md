---
title: HearthNet
emoji: 🔥
colorFrom: purple
colorTo: pink
sdk: gradio
sdk_version: 6.18.0
python_version: '3.10'
app_file: app.py
pinned: true
short_description: Community-Owned AI Mesh That Works When The Internet Doesn't
tags:
- backyard-ai
- tiny-titan
- best-agent
- nemotron
- minicpm
- modal
license: apache-2.0
---

# 🔥 HearthNet

### Community-Owned AI Mesh · Works When The Internet Doesn't

<p align="center">
  <strong>Local-First &nbsp;·&nbsp; Peer-to-Peer &nbsp;·&nbsp; Offline-Capable &nbsp;·&nbsp; Emergency-Ready</strong>
</p>

<p align="center">
  <a href="https://huggingface.co/spaces/build-small-hackathon/HearthNet"><img src="https://img.shields.io/badge/🤗%20HF%20Space-Live%20Demo-blue" alt="HF Space"></a>
  <a href="https://huggingface.co/Chris4K"><img src="https://img.shields.io/badge/HuggingFace-Chris4K-yellow" alt="HF Profile"></a>
  <a href="https://x.com/zX14_7"><img src="https://img.shields.io/badge/X-@zX14__7-black" alt="X"></a>
  <a href="https://github.com/ckal"><img src="https://img.shields.io/badge/GitHub-ckal-lightgrey" alt="GitHub"></a>
  <img src="https://img.shields.io/badge/model-SmolLM2--135M-green" alt="Model">
  <a href="#-testing--coverage"><img src="https://img.shields.io/badge/tests-932%20passing-brightgreen" alt="Tests"></a>
  <a href="#-testing--coverage"><img src="https://img.shields.io/badge/coverage-44%25-orange" alt="Coverage"></a>
</p>

> **Build Small Hackathon entry** — Backyard AI track · 🐜 Tiny Titan · 🤖 Best Agent
>
> 📺 **Demo video:** *(link before June 15)*
> 📣 **Social post:** *(link before June 15)*

---

## The Idea

What happens to your neighbourhood's AI when the power grid flickers, the ISP goes down, or the cloud API bill hits?

**HearthNet answers: nothing changes.** It keeps running.

Every household with a Raspberry Pi, an old laptop, or any device running Python becomes a **node**
in a local AI mesh. Nodes find each other automatically over Wi-Fi, share capabilities through a
routing bus, and keep working completely offline. When the internet returns, they sync up.
When it doesn't, they don't need it.

- A neighbourhood of 10 homes gets **10× the AI capacity** of any single device
- An offline community can still ask questions, share knowledge, send messages, and coordinate emergency response
- No cloud account, no API key, no monthly bill — hardware you already own

---

## Screenshots

<table>
<tr>
<td><strong>Ask the Mesh</strong><br><img src="docs/screenshots/US01-03-ask-response.png" alt="LLM routes query to best node" width="380"></td>
<td><strong>Live Peer Topology</strong><br><img src="docs/screenshots/US04-02-mesh-live-topology.png" alt="SVG peer graph" width="380"></td>
</tr>
<tr>
<td><strong>Routing Trace</strong><br><img src="docs/screenshots/US01-04-routing-trace.png" alt="Shows which node answered" width="380"></td>
<td><strong>Community Marketplace</strong><br><img src="docs/screenshots/US06-02-marketplace-after-post.png" alt="Post and browse offers" width="380"></td>
</tr>
<tr>
<td><strong>Direct Messages</strong><br><img src="docs/screenshots/US03-02-chat-sent.png" alt="Delivery confirmation" width="380"></td>
<td><strong>Invite QR Code</strong><br><img src="docs/screenshots/US05-03-settings-join-mesh.png" alt="Join mesh via QR" width="380"></td>
</tr>
<tr>
<td><strong>Emergency Mode</strong><br><img src="docs/screenshots/US08-01-emergency-tab.png" alt="Connectivity indicator" width="380"></td>
<td><strong>All 8 Tabs</strong><br><img src="docs/screenshots/US10-01-all-tabs-overview.png" alt="All tabs" width="380"></td>
</tr>
</table>

---

## 📦 Downloads & Builds

Get HearthNet for your platform:

| Platform | Download | Format | Size | Notes |
|----------|----------|--------|------|-------|
| **Android (PWA)** | [Web App](https://huggingface.co/spaces/build-small-hackathon/HearthNet) | Web | ~5MB | Install from browser - no download needed |
| **Android (Native)** | [app-debug.apk](https://huggingface.co/spaces/build-small-hackathon/HearthNet/resolve/main/build/android/HearthNetApp/platforms/android/app/build/outputs/apk/debug/app-debug.apk) | APK | 3.56MB | Native Android app via USB or direct install |
| **Windows Desktop** | [HearthNet.exe](https://huggingface.co/spaces/build-small-hackathon/HearthNet/resolve/main/dist/HearthNet.exe) | EXE | 212MB | Standalone executable - download & run |
| **Linux Desktop** | `python build/quickstart.py linux` | AppImage | ~120MB | Build on Linux or use script |
| **macOS Desktop** | `python build/quickstart.py macos` | .app | ~200MB | Native macOS app bundle |
| **Python (Any OS)** | [Source](https://github.com/ckal/HearthNet) | Python | - | `python app.py` - full mesh node |
| **Docker** | [Dockerfile](Dockerfile) | Container | 2GB | `docker run -p 7860:7860 hearthnet:latest` |
| **Guides & Docs** | [BUILD_GUIDE.md](docs/guides/BUILD_GUIDE.md) | Markdown | - | How to build for each platform |

**Recommended Paths:**
- 🚀 **Fastest** (5 min): PWA Web App - instant, no install
- 💻 **Desktop** (3 min): Download EXE/AppImage and run
- 🐳 **Server**: Docker container deployment
- 📚 See [BUILD_GUIDE.md](docs/guides/BUILD_GUIDE.md) for detailed instructions

---

## Quick Start

```bash
# Clone and install
git clone https://huggingface.co/spaces/build-small-hackathon/HearthNet
cd HearthNet
pip install -e ".[dev]"

# Run
python app.py          # open http://127.0.0.1:7860
```

### With Ollama (best quality)

```bash
ollama pull llama3.2:3b   # any Ollama model works
python app.py              # auto-detects Ollama, prefers it over SmolLM2
```

### On Android (PWA - Recommended)

```bash
# 1. Start HearthNet on your computer (Windows, Mac, or Linux)
python app.py

# 2. Find your computer IP address
# Windows: ipconfig | grep IPv4
# Mac/Linux: ifconfig | grep "inet " | grep -v 127

# 3. Open on Android device in Chrome/Firefox:
# http://<YOUR_IP>:7860

# 4. Tap menu → "Install app" or "Add to Home screen"
```

**📱 Full Android Setup Guide:** [ANDROID_DEPLOYMENT_GUIDE.md](docs/guides/ANDROID_DEPLOYMENT_GUIDE.md)
- ✅ PWA (instant, no build)
- 🔧 Native APK (optional, advanced)

### Connect your local node to the live HF Space

```bash
python -m hearthnet.cli invite redeem \
  "hnvite://v1/hf-space-1c95381d?host=build-small-hackathon-hearthnet.hf.space&port=443&transport=https&level=member"

python -m hearthnet.cli peers  # Space node should appear
```

---

## How It Works

### Capability Bus

Every feature is a **named capability** on the bus. Any node can call any capability;
the bus routes to the best available provider automatically:

```python
# LLM inference — routes to fastest/best node in the mesh
result = await bus.call("llm.chat", (1, 0), {
    "input": {"messages": [{"role": "user", "content": "What plants grow near water?"}]}
})

# RAG — routes to the node holding that corpus
result = await bus.call("rag.query", (1, 0), {
    "params": {"corpus": "community"},
    "input": {"query": "emergency water purification", "k": 3}
})

# Or from the CLI — no Python needed
python -m hearthnet.cli call llm.chat 1 0 '{"input":{"messages":[{"role":"user","content":"Hello!"}]}}'
python -m hearthnet.cli capabilities   # list all available capabilities across mesh
```

### Zero-Config Discovery

```bash
# Device 1 — already running
python app.py

# Device 2 — same Wi-Fi
python app.py
# Both nodes see each other in ~5 seconds (mDNS + UDP broadcast)
# No IP addresses, no router config, no firewall rules
```

### MoE Expert Routing (Best Agent)

Nodes advertise specialisations. Queries route to the best expert automatically:

```python
# A medical Raspberry Pi registers itself:
await bus.call("moe.register", (1, 0), {
    "input": {
        "expert_id": "model:medical-pi",
        "topic_tags": ["first_aid", "medication", "triage"],
        "confidence_score": 0.90,
    }
})

# Any node's medical query now routes there:
result = await bus.call("moe.route", (1, 0), {
    "input": {"query": "emergency first aid for burns", "top_k": 3}
})
# → {"candidates": [{"expert_id": "model:medical-pi", "score": 0.94}]}
```

### Offline Model Distribution

A node without internet pulls model weights from a LAN peer, chunk by chunk:

```python
models = await bus.call("model.list", (1, 0), {"input": {}})

job = await bus.call("model.pull", (1, 0), {
    "input": {"model_name": "llama3.2:3b", "source_node": "peer-id"}
})
# Progress via model.status; BLAKE3 content-addressed so never duplicated
```

---

## What Makes This "Tiny"

The HF Space demo uses **SmolLM2-135M** — 135 million parameters, ~270 MB RAM.

For local installs, any Ollama model works (1B–8B for significantly better quality).
The architecture is model-agnostic; the routing layer handles the rest.

**Real semantic RAG, not a toy:** when `sentence-transformers` is installed the
embedding service loads `BAAI/bge-small-en-v1.5` (~130 MB, CPU-friendly) so
`rag.query` performs genuine semantic retrieval. Without it, the service falls
back to a deterministic hash embedder and says so — no silent fakery.

**Why this qualifies for Tiny Titan:**
A full mesh of 10 Raspberry Pi 4 nodes (4 GB RAM each) can run:
- 135M model locally per node (always available, zero latency)
- Load-balanced routing for larger models across the mesh
- Full offline capability: discovery, RAG, chat, marketplace — no internet needed

---

## Architecture

```
┌───────────────────────────────────────────────────────────┐
│  Gradio UI (8 tabs)                                       │
│  Ask · Chat · Mesh · Marketplace · Files · Emergency ·    │
│  Settings · Getting Started                               │
└─────────────────────────┬─────────────────────────────────┘
                          │
             ┌────────────▼────────────┐
             │  Capability Bus (M03)   │
             │  route · score · trace  │
             └────┬──────┬──────┬──────┘
                  │      │      │
       ┌──────────▼┐  ┌──▼───┐ ┌▼──────────┐  ┌────────────┐
       │ LLM (M04) │  │ RAG  │ │ MoE (M27) │  │ Chat (M10) │
       │ Ollama    │  │(M05) │ │ Expert    │  │ Marketplace│
       │ llama.cpp │  │Chroma│ │ Registry  │  │ (M06) Files│
       │ HF Transfm│  │Embed │ └───────────┘  └────────────┘
       └─────┬─────┘  └──┬───┘
             └─────┬──────┘
    ┌──────────────▼──────────────────────────────────────┐
    │  Transport (X01) · Discovery (M02 mDNS/UDP)         │
    │  Events (X02 SQLite/Lamport) · E2E Encrypt (M23)    │
    │  Identity (M01 Ed25519) · Observability (X03)       │
    └─────────────────────────────────────────────────────┘
```

---

## Module Reference

<details>
<summary><strong>Phase 1 — Core (M01–M13, X01–X04) · 17 modules</strong></summary>

| Module | Description | Status |
|--------|-------------|--------|
| M01 | Node identity (Ed25519, manifests, canonical JSON) | ✅ |
| M02 | Peer discovery (mDNS, UDP broadcast, PeerRegistry) | ✅ |
| M03 | Capability bus (schema validation, routing, tracing) | ✅ |
| M04 | LLM service (Ollama, llama.cpp, HF Transformers, OpenAI fallback) | ✅ |
| M05 | RAG (chunker, ChromaDB, IngestPipeline, semantic search) | ✅ || M06 | Marketplace (event-sourced, Lamport-clocked posts) | ✅ |
| M07 | File blobs (BLAKE3 hash, content-addressed, chunked transfer) | ✅ |
| M08 | Gradio UI (8 tabs: Ask, Chat, Mesh, Marketplace, Files, Emergency, Settings, Getting Started) | ✅ |
| M09 | Emergency mode (async connectivity probe, auto-degrade on offline) | ✅ |
| M10 | Chat (event-backed 1:1 direct messaging, Lamport delivery order) | ✅ |
| M11 | Embeddings (embed.text, SentenceTransformer `bge-small-en-v1.5`, SimpleHashBackend fallback, batch support) | ✅ |
| M12 | CLI (click, ask / peers / marketplace / call / capabilities) | ✅ |
| M13 | Onboarding (invite QR, hnvite:// deep links, PyNaCl signing) | ✅ |
| X01 | Transport (FastAPI server, 12 REST endpoints, TLS) | ✅ |
| X02 | Events (SQLite, Lamport clocks, ReplayEngine, snapshots) | ✅ |
| X03 | Observability (structured JSON logging, metrics, distributed tracing) | ✅ |
| X04 | Config (typed frozen dataclasses, TOML, env overlay) | ✅ |

</details>

<details>
<summary><strong>Phase 2 — Advanced (M14–M25, X05–X07) · 18 modules</strong></summary>

| Module | Description | Status |
|--------|-------------|--------|
| M14 | Federation (bilateral cross-community trust, manifest signing) | ✅ |
| M15 | Relay tier (NAT traversal, keepalive, push token registry) | ✅ |
| M16 | Capability tokens (Ed25519 JWS-style hntoken://v1/ format) | ✅ |
| M17 | OCR (Tesseract + TrOCR backends, graceful degradation) | ✅ |
| M18 | Translation (NLLB backend, LRU cache, 4000-char limit) | ✅ |
| M19 | STT/TTS (Whisper local STT, Edge TTS synthesis) | ✅ |
| M20 | Vision (Florence-2 image describe, structured output) | ✅ |
| M21 | Tool calls (LLM mid-generation bus dispatch, ToolExecutor, plant_identify) | ✅ |
| M22 | Mobile native (Flutter contract, hnapp:// invites, push authority) | ✅ |
| M23 | E2E encryption (X3DH key agreement, Double Ratchet, AEAD envelope) | ✅ |
| M24 | Reranking (BGE + CrossEncoder backends, 100-doc limit) | ✅ |
| M25 | Group chat (ThreadService, ThreadViewStore, event-sourced threads) | ✅ |
| X05 | DHT (Kademlia node, 256-bucket routing table, bootstrap) | ✅ |
| X06 | WebSocket upgrade (bidirectional pubsub, WsClient) | ✅ |
| X07 | Federated metrics (NodeMetricsTick, MetricsAggregator, OTLP) | ✅ |

</details>

<details>
<summary><strong>Phase 3 — Experimental (M26–M31, X08–X09) · feature-flag gated</strong></summary>

| Module | Description | Status |
|--------|-------------|--------|
| M26 | Distributed inference (ShardDescriptor, PipelineOrchestrator, model.pull) | registered |
| M27 | MoE routing (ExpertRegistry, MoeRouter, moe.route/register/list) | registered |
| M28 | Federated learning (FedLearnCoordinator, RoundManifest, gradient aggregation) | experimental |
| M29 | LoRa beacons (32-byte frames, 868 MHz offline signaling) | experimental |
| M30 | Evidence graph / EBKH (ClaimStore, attestations, disputes) | experimental |
| M31 | Civil defense NRW (AuditChain, role certs, structured alerts) | experimental |
| X08 | Tensor transport (chunked binary tensor streaming) | experimental |
| X09 | Conformance suite (protocol test harness) | experimental |

</details>

---

## Local AI Backends

No mocks. No fake responses. Real local inference only.

| Backend | Activation | Notes |
|---------|-----------|-------|
| **Ollama** (preferred) | `ollama pull llama3.2:3b` + auto-detect | 70+ models, zero config |
| **llama.cpp** | Start server on port 8080 + auto-detect | Any GGUF model |
| **HF Transformers** | Default on HF Space (no config needed) | SmolLM2-135M default |
| **NVIDIA Nemotron** | `NVIDIA_API_KEY` env var | opt-in cloud; nemotron-70b/super-49b/mini-4b |
| **OpenBMB / MiniCPM** | `MINICPM_URL` env var (local NIM/llama.cpp) | local-first, OpenAI-compatible |
| **Modal** | `MODAL_ENDPOINT` env var | opt-in serverless GPU |
| **OpenAI API** | `OPENAI_API_KEY` env var | opt-in online fallback only |

All configured backends are registered on a single `llm.chat` / `llm.complete`
capability that advertises every served model in `params["models"]`; the caller
selects a model by name and the bus dispatches to the owning backend. Local
backends are always preferred; sponsor/cloud backends activate only when their
env var is set.

If nothing is available: `{"status": "unavailable"}` + clear UI message. Never fabricated.

---

## Security

- **Ed25519** — all node manifests and invite links signed with PyNaCl
- **X3DH + Double Ratchet** — end-to-end encrypted chat (M23)
- **BLAKE3** — content-addressed file blobs (tamper-evident)
- **localhost-only CLI** — all admin HTTP restricted to 127.0.0.1
- **Bandit HIGH findings: 0** (verified in CI)

---

## Tests

```bash
python -m pytest tests/ -q                                            # 548 tests
python -m pytest tests/ --ignore=tests/test_e2e_user_stories.py -q  # skip Playwright
```

| Suite | Count | What it covers |
|-------|-------|----------------|
| Phase 1 core | 25 | Bus routing, emergency mode, snapshot, wiring |
| Phase 2 advanced | 40+ | Crypto, tokens, federation, OCR, DHT, group chat |
| Phase 3 experimental | 15 | MoE, distributed inference, fedlearn, LoRa, evidence |
| Integration (real services) | 60+ | RAG pipeline, LLM routing, marketplace, file blobs |
| UI regression | 6 | Tab build without NameError (HF Space crash guard) |
| E2E Playwright + API | 38 | All 8 tabs, Gradio API, user story flows, mesh connection |
| **Total** | **548** | Python 3.13 · pytest-asyncio 0.26 |

---

## Hackathon Entry

**Track:** 🏕️ Backyard AI (Practical)

**Badges targeted:**

| Badge | Why |
|-------|-----|
| 🐜 **Tiny Titan** | Runs on SmolLM2-135M (135M params). Full mesh on Raspberry Pi 4. |
| 🤖 **Best Agent** | MoE routing + capability bus = distributed agentic AI across a mesh. Nodes specialise and route autonomously. |
| 🎨 **Off Brand** | `app_nemotron.py` — custom purple-to-orange gradient UI, branded badge chips, Google Inter font. |

**Sponsor prizes targeted:**

| Prize | Why |
|-------|-----|
| 🟢 **NVIDIA Nemotron Hardware Prize** (RTX 5080) | `app_nemotron.py` — full Nemotron document intelligence Space. Structured extraction, Q&A, summarisation, push to mesh RAG. Uses `nvidia/llama-3.1-nemotron-nano-8b-instruct`. |
| 🔵 **OpenBMB MiniCPM Best Build** ($2,500) | `MiniCPM` backend auto-detected via `MINICPM_URL` env var. `openbmb/MiniCPM4-8B` and `MiniCPM3-4B` supported out of the box. |
| ⚫ **Modal Best Use** ($10k credits) | `ModalBackend` in `hearthnet/services/llm/backends/modal_backend.py`. Deploy with `scripts/modal_deploy.py`, set `MODAL_ENDPOINT` env var. |

**Why this fits Backyard AI:**
- Practical: solves real community resilience and emergency preparedness
- Local: runs on hardware people already own, zero cloud dependency
- Problem-solving: communications and AI when infrastructure fails

---

## Contributing & Docs

| Resource | Link |
|----------|------|
| Architecture | [ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| System overview | [docs/00-OVERVIEW.md](docs/00-OVERVIEW.md) |
| Capability contract | [docs/CAPABILITY_CONTRACT.md](docs/CAPABILITY_CONTRACT.md) |
| Roadmap | [docs/roadmap.md](docs/roadmap.md) |
| Task tracker | [tasks.md](tasks.md) |
| Phase 2+3 specs | [docs/p2_p3/](docs/p2_p3/) |

---

## 🧪 Testing & Coverage

### Test Suite: 932 Tests, 100% Pass Rate

HearthNet has **comprehensive test coverage** across all modules:

| Category | Tests | Status | Reports |
|----------|-------|--------|---------|
| **Phase 1 Core** (M01-M13, X01-X04) | 343 | ✅ Implemented | [M01-M13 Tests](tests/test_m*_spec.py) |
| **LLM Service** (M04) | 72 | ✅ Enhanced (50→75%+) | [M04 Enhanced](tests/test_m04_enhanced.py) |
| **RAG Service** (M05) | 57 | ✅ Enhanced (40→75%+) | [M05 Enhanced](tests/test_m05_enhanced.py) |
| **Observability** (X03) | 63 | ✅ Enhanced (48→75%+) | [X03 Enhanced](tests/test_x03_enhanced.py) |
| **Transport** (X01) | 69 | ✅ Enhanced (12→55%+) | [X01 Enhanced](tests/test_x01_enhanced.py) |
| **Phase 2/3 Specs** (M14-M32, X05-X09) | 216 | 🏗️ Scaffolded | [P2/P3 Tests](tests/test_m1[4-9]_spec.py), [X0[5-9]](tests/test_x0[5-9]_spec.py) |
| **Reference Docs** | 80 | 🏗️ Scaffolded | [API Contract](tests/test_capability_contract.py), [Glossary](tests/test_glossary.py) |
| **Total** | **932** | **100% Pass** | [Full Report](docs/reports/TEST_SUITE_REPORT.md) |

**Code Coverage: 44% (6,043 / 10,743 lines)**
- Well-covered (>70%): Identity, Bus, Types, UI core
- Moderate (40-70%): LLM, RAG, Chat
- Target for improvement: Transport server, backends, UI advanced

### Run Tests Locally

```bash
# Install test dependencies
pip install -r requirements-dev.txt

# Run all tests
python -m pytest tests/ -v

# Run with coverage report
python -m pytest tests/ --cov=hearthnet --cov-report=html --cov-report=term
# Open: htmlcov/index.html

# Run specific module
python -m pytest tests/test_m04_enhanced.py -v

# Run before commit (git hook)
bash pre-commit-hook.sh
```

### CI/CD Pipeline

**Automatic testing on:**
- ✅ Every push to `main` / `dev` branches
- ✅ Every pull request
- ✅ Before commit (local pre-commit hook)

**Configuration:** [.github/workflows/test.yml](.github/workflows/test.yml)

**Setup local pre-commit hook:**
```bash
cp pre-commit-hook.sh .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit

# Now tests run automatically before each commit
git commit -m "my changes"  # ← tests run first!
```

### Test Documentation

- **Full Report:** [TEST_SUITE_REPORT.md](docs/reports/TEST_SUITE_REPORT.md) — 783 tests, all modules
- **Coverage Enhancement:** [COVERAGE_ENHANCEMENT_REPORT.md](COVERAGE_ENHANCEMENT_REPORT.md) — 149 new tests for M04/M05/X01/X03
- **Test Structure:** Each test follows Happy / Error / Edge pattern
- **No Mocks:** All implemented tests use real code paths
- **Integration Tests:** Cross-service messaging and capabilities

---

## 🔗 Deployment & Source


| Resource | Purpose |
|----------|---------|
| **HF Space** (Primary) | [https://huggingface.co/spaces/build-small-hackathon/HearthNet](https://huggingface.co/spaces/build-small-hackathon/HearthNet) | Live demo + Downloads |
| **GitHub** (Mirror/CI) | [https://github.com/ckal/HearthNet](https://github.com/ckal/HearthNet) | Source control + Issue tracking |

**Deployment Architecture:**
- 📡 **HF Space**: Live demo, PWA app, binary downloads (exe, apk, etc.)
- 🐙 **GitHub**: Source repository, CI/CD, releases, issue tracking
- 🔄 **Sync**: Changes push to both simultaneously

**Build Artifacts Available:**
- Windows EXE: [dist/HearthNet.exe](https://huggingface.co/spaces/build-small-hackathon/HearthNet/resolve/main/dist/HearthNet.exe) (212 MB)
- Android APK: [build/android/.../app-debug.apk](https://huggingface.co/spaces/build-small-hackathon/HearthNet/resolve/main/build/android/HearthNetApp/platforms/android/app/build/outputs/apk/debug/app-debug.apk) (3.56 MB)
- Build scripts: [BUILD_GUIDE.md](docs/guides/BUILD_GUIDE.md) for EXE, AppImage, .app, Docker

---

## Links

| | |
|--|--|
| 🤗 HF Space (Live) | https://huggingface.co/spaces/build-small-hackathon/HearthNet |
| 🐙 GitHub (Source) | https://github.com/ckal/HearthNet |
| 👤 HF Profile | https://huggingface.co/Chris4K |
| 🐦 X / Twitter | https://x.com/zX14_7 |
| 💻 GitHub Profile | https://github.com/ckal |

---

<p align="center">
  Built with open source models and the belief that communities should own their AI.<br>
  <em>Small model. Big mesh. Real resilience.</em>
</p>