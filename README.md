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
  <a href="https://huggingface.co/spaces/build-small-hackathon/HearthNet"><img src="https://img.shields.io/badge/🤗%20HF%20Space-Live-blue" alt="HF Space"></a>
  <a href="https://github.com/ckal/HearthNet"><img src="https://img.shields.io/badge/GitHub-source-black" alt="GitHub"></a>
  <img src="https://img.shields.io/badge/python-3.13%2B-blue" alt="Python 3.13+">
  <img src="https://img.shields.io/badge/license-Apache%202.0-green" alt="License">
  <img src="https://img.shields.io/badge/backends-llama.cpp%20|%20Ollama-orange" alt="Backends">
  <img src="https://img.shields.io/badge/routing-intelligent%20mesh-purple" alt="Routing">
  <a href="#-testing--coverage"><img src="https://img.shields.io/badge/tests-390%2B%20passing-brightgreen" alt="Tests"></a>
  <a href="#features"><img src="https://img.shields.io/badge/features-routing%20trace-teal" alt="Routing Trace"></a>
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
in a local AI mesh. Nodes find each other automatically over Wi-Fi, share capabilities through an
intelligent routing bus, and work **completely offline**. When the internet is available, nodes **automatically route requests to the best provider** — whether local, nearby on LAN, or across the internet via relay. You see exactly which node answered.

- A neighbourhood of 10 homes gets **10× the AI capacity** of any single device
- **Offline-first**: all features work without internet; internet is optional for mesh expansion
- **Transparent routing**: every Ask/Chat/RAG request shows which node served it (local or remote)
- Ask questions, share knowledge, send messages, coordinate emergency response — all offline
- No cloud account, no API key, no monthly bill — hardware you already own

---

## Features

### 🧠 Intelligent Routing (NEW)
When you ask a question, the bus scores available LLM nodes by latency, load, and reliability. Your request goes to the **best node right now** — whether it's local, your neighbour's device, or a peer across the internet. Failover is automatic: if the preferred node can't help, the next-best provider takes over **invisibly**.

**Routing Trace** shows you exactly where your request was served:
- 🏠 **Local**: Answered by this device
- 🌐 **Remote (node-id)**: Routed to a peer node (LAN or internet)
- ❌ **Error**: No suitable provider found

### 💬 Chat Over LAN & Internet
Direct 1:1 messages work completely offline on your Wi-Fi. Connect to the internet (via relay hub on HF Space) and chat with anyone in the mesh, regardless of network. No accounts, no passwords—just show them your QR code.

### 🔍 Federated RAG
Share a corpus of documents with your community. Any node can search across **all available corpora** automatically, with results ranked by relevance. Works offline on local copies; syncs and queries remote corpora when internet is available.

### 🤖 MOE Expert Routing
Nodes advertise their specialisations. Queries automatically route to the best experts in your mesh for better answers.

### 🚨 Emergency Mode
When connectivity drops, the UI automatically switches to degraded mode. Nodes keep working offline. When restored, changes sync. Perfect for neighbourhood coordination during outages.

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

### With llama.cpp (recommended — fast, offline)

```bash
# 1. Download a GGUF model
wget https://huggingface.co/lmstudio-community/Meta-Llama-3.1-8B-Instruct-GGUF/resolve/main/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf

# 2. Start llama.cpp server
./llama-server -m Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf -p 8080

# 3. Run HearthNet (auto-detects llama.cpp on port 8080)
python app.py
```

**Why llama.cpp?**
- ⚡ Fast inference on CPU (no GPU required)
- 💾 Runs the best models offline (8B params fits on 16GB RAM)
- 🔧 GGUF format is efficient and portable
- 🌍 No API key, no cloud, no latency

### Alternative: Ollama

```bash
ollama pull llama3.2:3b   # any Ollama model works
python app.py              # auto-detects Ollama
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
# Get an invite code from the Space Settings tab
# Then redeem it locally:
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

### Intelligent Routing & Failover

When you ask a question:
1. **Scoring**: Bus evaluates all LLM providers by latency, load, reliability, and local preference
2. **Selection**: Request goes to the best provider
3. **Failover**: If that node can't help (error or unavailable), automatically try the next-best alternative
4. **Tracing**: Result includes `_routed_via` showing which node served it

```python
# Node A has no LLM backend (would normally fail)
# Node B has llama.cpp running
# You ask Node A a question → Node A routes to Node B → B answers → A shows you the result
# Tracing shows: "_routed_via": "node-b-id"

result = await bus.call("llm.chat", (1, 0), {...})
# result includes "_routed_via": "node-b-id"  ← Shows the true origin
```

### MoE Expert Routing

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

For local installs, any GGUF model works (1B–8B for significantly better quality).
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

## Local AI Backends

**No mocks. No fake responses. Real local inference only.**

HearthNet prioritizes local, private models. Cloud backends are **opt-in only** (env vars).

### Local Backends (Primary)

| Backend | Activation | Notes |
|---------|-----------|-------|
| **llama.cpp** (recommended) | Start server on port 8080 + auto-detect | Any GGUF model; fastest on CPU |
| **Ollama** | `ollama pull llama3.2:3b` + auto-detect | 70+ models, easy management |
| **HF Transformers** | Default on HF Space (no config needed) | SmolLM2-135M, CPU-friendly |
| **OpenBMB / MiniCPM** | `MINICPM_URL` env var (local server) | Local-first, OpenAI-compatible API |

### Optional Cloud Backends (Opt-In via Env Vars)

| Backend | Activation | Notes |
|---------|-----------|-------|
| **NVIDIA Nemotron** | `NVIDIA_API_KEY` env var | For RTX nodes: nemotron-70b/mini-4b |
| **Modal** | `MODAL_ENDPOINT` env var | Serverless GPU inference |
| **OpenAI API** | `OPENAI_API_KEY` env var | Fallback only; not recommended for offline mesh |

All configured backends are registered on the `llm.chat` capability. The routing bus selects the best backend based on:
1. **Local first**: llama.cpp, Ollama, HF Transformers always preferred
2. **Load & latency**: If you have multiple local nodes, asks route to the least-busy one
3. **Failover**: If local is unavailable and you have internet, remote nodes or cloud backends are tried

If no suitable backend is available: clear error message returned. Never silent, never fabricated.

---

## Security

- **Ed25519** — all node manifests and invite links signed with PyNaCl
- **X3DH + Double Ratchet** — end-to-end encrypted chat (M23)
- **BLAKE3** — content-addressed file blobs (tamper-evident)
- **localhost-only CLI** — all admin HTTP restricted to 127.0.0.1
- **Bandit HIGH findings: 0** (verified in CI)

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
       │llama.cpp  │  │(M05) │ │ Expert    │  │ Marketplace│
       │ Ollama    │  │Chroma│ │ Registry  │  │ (M06) Files│
       │HF Transfm │  │Embed │ └───────────┘  └────────────┘
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
| M04 | LLM service (llama.cpp, Ollama, HF Transformers, cloud fallback) | ✅ |
| M05 | RAG (chunker, ChromaDB, IngestPipeline, semantic search) | ✅ |
| M06 | Marketplace (event-sourced, Lamport-clocked posts) | ✅ |
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

## 🧪 Testing & Coverage

### Comprehensive Test Suite: 390+ Tests

HearthNet includes rigorous tests for all core capabilities:

| Suite | Count | Coverage |
|-------|-------|----------|
| **Phase 1 Core** (M01-M13, X01-X04) | 120+ | Bus routing, discovery, identity, emergency mode |
| **Intelligent Routing** (NEW) | 8+ | Failover, latency scoring, tracing, stamping |
| **Chat & Messaging** (M10) | 35+ | Direct messages, cross-node delivery, event-sourced |
| **RAG & Search** (M05) | 25+ | Local corpus, semantic search, federated queries |
| **LLM Service** (M04) | 20+ | Multiple backends (llama.cpp, Ollama, HF), model selection |
| **Integration** | 40+ | Real services wired together, marketplace, file blobs |
| **UI & E2E** | 20+ | All 8 tabs, Gradio API, user workflows |
| **Phase 2/3 Advanced** | 70+ | Federation, crypto, DHT, MoE, group chat |
| **Total** | **390+** | Python 3.13 · pytest-asyncio · Full async test suite |

### Run Tests Locally

```bash
# Full suite
python -m pytest tests/ -v

# Specific module (e.g., routing tests)
python -m pytest tests/test_bus_failover.py -v

# With coverage report
python -m pytest tests/ --cov=hearthnet --cov-report=term-missing

# Skip slow E2E tests
python -m pytest tests/ --ignore=tests/test_e2e_user_stories.py -v
```

**All tests pass** on Python 3.13 with pytest-asyncio.

**Focus areas:**
- ✅ Well-covered: Bus routing, identity, chat, discovery, emergency mode
- 🎯 Strong: LLM service, RAG pipeline, marketplace, event system
- 📈 Expanding: Transport layer, UI advanced features, observability metrics

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

## Hackathon Entry

**Track:** 🏕️ Backyard AI (Practical)

**Why HearthNet wins:**

🐜 **Tiny Titan:** Runs on SmolLM2-135M (135M params). Full mesh on Raspberry Pi 4. Every device runs real inference locally.

🤖 **Best Agent:** Capability bus + intelligent routing = distributed agentic system. Nodes score, select, and failover to the best provider autonomously. MOE expert routing means each specialist node attracts the right queries.

**Optional integrations:**
- NVIDIA Nemotron: Document intelligence for RAG (`NVIDIA_API_KEY` env var)
- OpenBMB MiniCPM: Local-first models via `MINICPM_URL` (llama.cpp-compatible)
- Modal: Serverless GPU as remote node (`MODAL_ENDPOINT` env var)

---

## Links

| | |
|--|--|
| 🤗 HF Space (Live) | https://huggingface.co/spaces/build-small-hackathon/HearthNet |
| 🐙 GitHub (Source) | https://github.com/ckal/HearthNet |
| 📚 Architecture | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| 🧪 Tests | `python -m pytest tests/ -v` |

---

<p align="center">
  Built with open source models and the belief that communities should own their AI.<br>
  <em>Small model. Big mesh. Real resilience.</em>
</p>
