# HearthNet — Architecture Reference

> **Local-first community AI mesh.** Each participant runs a node on their own hardware.
> Nodes discover each other automatically and share AI capabilities, files, and community
> posts — no central server required.

---

## High-Level Concept

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         Community Mesh (LAN / overlay)                    │
│                                                                           │
│   ┌─────────────┐    mDNS/UDP     ┌─────────────┐    mDNS/UDP            │
│   │  Node A     │◄───────────────►│  Node B     │◄──────────────         │
│   │  (anchor)   │                 │  (hearth)   │                         │
│   │             │   capability    │             │                         │
│   │  CapBus ◄───┼─────bus.call───►─►  CapBus   │                         │
│   │  LLM svc    │                 │  RAG svc    │                         │
│   │  RAG svc    │                 │  OCR svc    │                         │
│   │  Gradio UI  │                 │  Gradio UI  │                         │
│   └─────────────┘                 └─────────────┘                         │
└──────────────────────────────────────────────────────────────────────────┘
```

HearthNet is structured around three ideas:

1. **Node** — a Python process on someone's hardware (Raspberry Pi, laptop, server).
2. **CapabilityBus** — a message bus where services register *capabilities* (e.g. `llm.chat@1.0`). Any code, local or remote, calls a capability by name.
3. **Services** — pure-Python objects that handle capability calls. A node installs whichever services its hardware supports.

---

## Module Map

### Phase 1 — Foundation

| Module | Location | What it does |
|--------|----------|-------------|
| **M01 Identity** | `hearthnet/identity/` | Ed25519 node keys, community manifests, invite tokens |
| **M02 Discovery** | `hearthnet/discovery/` | mDNS + UDP multicast peer discovery |
| **M03 Bus** | `hearthnet/bus/` | Capability router, health ring buffer, trust levels |
| **M04 LLM** | `hearthnet/services/llm/` | Local model backends (Ollama, llama.cpp, LM Studio, HF, Anthropic) |
| **M05 RAG** | `hearthnet/services/rag/` | Chunker → embedder → Chroma vector store + retrieval |
| **M06 Marketplace** | `hearthnet/services/marketplace/` | Event-sourced community board (posts, offers, requests) |
| **M07 Blobs** | `hearthnet/blobs/` | BLAKE3 content-addressed file store with chunked transfer |
| **M08 UI** | `hearthnet/ui/` | Gradio 8-tab interface + themes + topology component |
| **M09 Emergency** | `hearthnet/emergency/` | Async probe loop → emergency state machine |
| **M10 Chat** | `hearthnet/services/chat/` | Event-backed direct messages between nodes |
| **M11 Embedding** | `hearthnet/services/embedding/` | Sentence-transformer embeddings (BAAI/bge-small) |
| **M12 CLI** | `hearthnet/cli.py` | Click CLI: run, call, log, rag, invite, version, … |
| **M13 Onboarding** | `hearthnet/ui/onboarding.py` | Invite QR flow + first-run wizard |

### Phase 2 — Resilience & Rich Services

| Module | Location | What it does |
|--------|----------|-------------|
| **M14 Federation** | `hearthnet/federation/` | Cross-community node manifests + signed bridges |
| **M15 Relay** | `hearthnet/relay/` | Public-IP relay tier for NAT traversal |
| **M16 Tokens** | `hearthnet/identity/tokens.py` | AuthToken / CapabilityToken scoped access |
| **M17 OCR** | `hearthnet/services/ocr/` | Tesseract / TrOCR text extraction |
| **M18 Translation** | `hearthnet/services/translation/` | NLLB-200 local translation |
| **M19 STT/TTS** | `hearthnet/services/stt_tts/` | Whisper STT + Coqui/pyttsx3 TTS |
| **M20 Vision** | `hearthnet/services/vision/` | Florence-2 image captioning / VQA |
| **M21 Tool Calls** | `hearthnet/services/tools/` | LLM tool-call executor (plant ID, search, …) |
| **M22 Mobile** | `hearthnet/ui/mobile/` | PWA manifest + service worker for home-screen install |
| **M23 E2E Encryption** | `hearthnet/crypto/` | X25519 ECDH + ChaCha20-Poly1305 channel encryption |
| **M24 Rerank** | `hearthnet/services/rerank/` | Cross-encoder reranking for RAG results |
| **M25 Group Chat** | `hearthnet/services/group_chat/` | Multi-party room-based chat |

### Phase 3 — Experimental (opt-in via `config.toml`)

| Module | Location | Flag | What it does |
|--------|----------|------|-------------|
| **M26 Distributed Inference** | `hearthnet/distributed_inference/` | `research.distributed_inference` | Layer-shard a 7B model across LAN nodes (Petals-style) |
| **M27 MoE Routing** | `hearthnet/moe/` | `research.moe_routing` | Route queries to best expert (model/service/human) via learned scorer |
| **M28 FedLearn** | `hearthnet/fedlearn/` | `research.fedlearn` | FedAvg LoRA fine-tuning without sharing raw data |
| **M29 LoRa Beacons** | `hearthnet/lora/` | `research.lora_beacons` | 868 MHz offline "I'm alive" heartbeats via USB LoRa stick |
| **M30 Evidence Graph** | `hearthnet/evidence/` | `research.evidence` | Claim → attest → dispute provenance graph + EBKH bridge |
| **M31 Civil Defense** | `hearthnet/civdef/` | `research.civil_defense` | THW/DRK/KatS alert pipeline with role certs + audit chain |
| **M32 Protocol Standard** | `hearthnet/services/protocol/` | on by default | Protocol version list + conformance report |

### Cross-Cutting

| ID | Location | What it does |
|----|----------|-------------|
| **X01 Transport** | `hearthnet/transport/` | HTTP/SSE client, backpressure, rate limiting, frame types |
| **X02 Events** | `hearthnet/events/` | SQLite Lamport event log + gossip sync |
| **X03 Observability** | `hearthnet/observability/` | Tracing, metrics, Doctor health checks, TrackioExporter |
| **X04 Config** | `hearthnet/config.py` | Typed TOML config + ResearchConfig feature flags |
| **X05 DHT** | `hearthnet/dht/` | Kademlia-inspired DHT for cross-LAN peer lookup |
| **X06 WebSocket** | `hearthnet/transport/` | WebSocket pubsub (StateBus → live UI push) |
| **X07 Federated Metrics** | `hearthnet/observability/` | Opt-in aggregate mesh health metrics |
| **X08 Tensor Transport** | `hearthnet/transport/tensor/` | Chunked tensor stream for M26 distributed inference |
| **X09 Conformance Suite** | `hearthnet/conformance/` | 21-check black-box conformance runner |

---

## Composition Root

`HearthNode` in [hearthnet/node.py](hearthnet/node.py) is the single composition root.

```python
node = HearthNode(
    node_id="my-node",
    display_name="Alice's Pi",
    community_id="ed25519:abc123",
)
node.install_services(corpus="general")
await node.start()
```

`install_services()` registers all services the local hardware supports into the bus. Heavy optional dependencies (torch, chromadb, etc.) are imported lazily and fail gracefully — a node with no GPU still works, it just can't answer GPU-only capabilities.

---

## Capability Bus

```
Caller ──── bus.call(name, version, body) ──────────┐
                                                     ▼
                                          ┌──────────────────┐
                                          │  CapabilityBus   │
                                          │                  │
                                          │  Registry        │
                                          │  ┌─────────────┐ │
                                          │  │ local route │─┼──► Service.handle()
                                          │  ├─────────────┤ │
                                          │  │ remote route│─┼──► HTTP POST /bus/v1/call
                                          │  └─────────────┘ │
                                          │  HealthMonitor   │
                                          │  TrustFilter     │
                                          └──────────────────┘
```

- **Local route** — service is installed on this node → direct Python call.
- **Remote route** — capability is advertised by a peer → HTTP POST to that peer's transport.
- **Version negotiation** — capabilities are registered with a `(major, minor)` version; the bus picks the highest compatible version.
- **Health monitoring** — each service's response times are tracked in a ring buffer; unhealthy services are quarantined for `BUS_QUARANTINE_SECONDS`.

---

## Data Flow: LLM Chat Request

```
User types in Gradio UI
       │
       ▼
  app.py (Gradio event handler)
       │  bus.call("llm.chat@1.0", body)
       ▼
  CapabilityBus.call()
       │
       ├─ local LlmService found?
       │       │ yes → LlmService.handle() → backend.chat() → yield Token
       │       │
       └─ no local service
               │ peer has llm.chat?
               ├─ yes → HTTP POST /bus/v1/call → remote node → stream tokens back
               └─ no  → CapabilityError("not_found")
```

---

## Discovery Flow

```
Node boots
    │
    ├── mDNS: register _hearthnet._tcp.local.  (LAN multicast DNS)
    ├── UDP: send announce to 224.0.0.251:7079 every 15s
    │
    ▼
PeerRegistry receives announcements from other nodes
    │
    ├── new peer → RegistryEvent(kind="added", entry=...)
    ├── peer gone (TTL expired) → RegistryEvent(kind="removed", ...)
    └── ManifestPublisher re-publishes every 300s
```

---

## Emergency Mode

```
EmergencyDetector (async loop, 30s probe)
    │
    ├── probe connectivity endpoints
    │
    ├── ONLINE  → EmergencyState.NORMAL
    │                │ UI shows normal theme
    │
    └── OFFLINE → EmergencyState.EMERGENCY
                     │ UI switches to emergency theme (red)
                     │ emergency.llm.chat capability activated
                     │ LoRa beacons sent if hardware available (M29)
                     │ Civil defense alerts published if role cert present (M31)
```

---

## MoE Expert Routing (M27)

```
Query arrives at any node
       │
       ▼
  MoeRouter.route(query, top_k=3)
       │
       ├── score all registered ExpertDescriptors against query
       │   (tag overlap + cosine similarity + recency weighting)
       │
       └── return ranked RouteResult
              │
              ├── expert_type="model"   → bus.call(f"llm.chat@1.0", ...) on that node
              ├── expert_type="service" → bus.call(expert_capability, ...)
              ├── expert_type="human"   → notify via chat + start handoff timer (M27 §4)
              └── expert_type="external"→ HTTP call to opt-in external API
```

Enable it: set `research.moe_routing = true` in `~/.config/hearthnet/config.toml`.

---

## Distributed Inference (M26 — BitTorrent-style LLM sharing)

```
Node A: layers 0–15 of Llama-3.2-3B
Node B: layers 16–27 of Llama-3.2-3B
Node C: layers 28–35 (lm_head) of Llama-3.2-3B
                │
                ▼
PipelineOrchestrator.plan(model_id="llama3.2:3b")
    │  → discovers shards via experimental.distributed_llm.shard.list
    │  → checks layer coverage: 0..35 ✓
    │
PipelineOrchestrator.run(pipeline, input_tokens)
    │  → sends activations A→B via X08 TensorTransport (1 MiB chunks)
    │  → B sends activations B→C
    │  → C returns final logits
    │
    └── caller gets streamed tokens like any local model
```

Model weights are shared chunk-by-chunk using BLAKE3 CID-addressed blob transfer — same
mechanism as file blobs (M07), but optimised for `.gguf` / `.safetensors` files.

---

## File Tree

```
hearthnet/
├── node.py                    # HearthNode — composition root
├── types.py                   # Shared type aliases (NodeID, ShardID, AlertID, …)
├── constants.py               # All numeric defaults and limits
├── config.py                  # HearthnetConfig + ResearchConfig (TOML-backed)
├── cli.py                     # Click CLI entry point
├── facades.py                 # HearthFacade — thin high-level API for app.py
├── controller.py              # HearthController — legacy thin wrapper
│
├── bus/                       # M03 CapabilityBus
│   ├── router.py              # routing logic (local → remote)
│   ├── registry.py            # CapabilityEntry, RegistryEvent, Diff
│   ├── capability.py          # CapabilityEntry dataclass
│   └── health.py              # ring-buffer health monitor
│
├── identity/                  # M01
│   ├── keys.py                # Ed25519 key generation + signing
│   ├── manifest.py            # NodeManifest, CommunityManifest, CommunityPolicy, …
│   └── tokens.py              # AuthToken, CapabilityToken
│
├── discovery/                 # M02
│   └── peers.py               # mDNS + UDP multicast PeerRegistry
│
├── transport/                 # X01 / X06 / X08
│   ├── client.py              # HTTP + SSE client
│   ├── streams.py             # Frame, SseReader
│   ├── backpressure.py        # FlowControl, RateCheck, RateLimiter
│   └── tensor/                # X08 tensor chunked transport
│
├── events/                    # X02
│   ├── log.py                 # SQLite Lamport event log
│   └── sync.py                # Gossip SyncClient / SyncServer
│
├── observability/             # X03
│   ├── tracing.py             # attach/detach trace context
│   ├── metrics.py             # MetricsCollector, TrackioExporter
│   └── doctor.py             # DoctorResult, CheckResult, DoctorService
│
├── services/                  # M04 – M21 + M32
│   ├── llm/                   # M04 — backends: ollama, llama_cpp, lmstudio, hf_api, anthropic
│   ├── rag/                   # M05
│   ├── marketplace/           # M06
│   ├── chat/                  # M10
│   ├── embedding/             # M11
│   ├── ocr/                   # M17
│   ├── translation/           # M18
│   ├── stt_tts/               # M19
│   ├── vision/                # M20
│   ├── tools/                 # M21
│   ├── group_chat/            # M25
│   └── protocol/              # M32
│
├── ui/                        # M08
│   ├── app.py                 # Gradio 8-tab entry point
│   ├── tabs/                  # one file per tab
│   ├── theme.py               # hearthnet_theme, emergency_theme
│   ├── topology.py            # TopologyComponent (mesh graph)
│   ├── onboarding.py          # first-run wizard + invite QR
│   └── mobile/                # M22 PWA manifest + service worker
│
├── emergency/                 # M09
│   ├── detector.py            # async probe loop
│   └── state.py               # EmergencyState enum
│
├── crypto/                    # M23
│   └── channel.py             # X25519 + ChaCha20-Poly1305
│
├── blobs/                     # M07
│   └── store.py               # BLAKE3 CID store + chunked reader
│
├── dht/                       # X05
├── federation/                # M14
├── relay/                     # M15
│
├── distributed_inference/     # M26 (experimental)
├── moe/                       # M27 (experimental)
├── fedlearn/                  # M28 (experimental)
├── lora/                      # M29 (experimental)
├── evidence/                  # M30 (experimental)
├── civdef/                    # M31 (experimental)
└── conformance/               # X09
```

---

## Configuration

`~/.config/hearthnet/config.toml` (created on first run with defaults):

```toml
[node]
node_id      = ""          # auto-generated Ed25519 key ID
display_name = "My Node"
data_dir     = "~/.hearthnet"

[transport]
http_port    = 7080
ui_port      = 7860

[llm]
default_backend = "ollama"   # "ollama" | "llama_cpp" | "lmstudio" | "hf_api" | "smollm"

[rag]
corpus_dir      = "~/.hearthnet/corpus"
embedding_model = "BAAI/bge-small-en-v1.5"

[policy.research]
enable                  = false     # master switch for all experimental modules
moe_routing             = false     # M27
distributed_inference   = false     # M26
fedlearn                = false     # M28
lora_beacons            = false     # M29
evidence                = false     # M30
civil_defense           = false     # M31
```

---

## Connecting a Local Node to the HF Space

The HF Space at `https://huggingface.co/spaces/build-small-hackathon/HearthNet` is a
single-node anchor you can peer with from any local machine.

```bash
# 1. Clone and install
git clone https://huggingface.co/spaces/build-small-hackathon/HearthNet
cd HearthNet
pip install -e .

# 2. Run your local node (pick a free port if 7080 is taken)
python -m hearthnet.cli run --http-port 7080 --ui-port 7860

# 3. Manually add the HF Space anchor as a peer (different network = manual)
python -m hearthnet.cli call discovery.peer.add 1 0 \
  '{"endpoint":"https://build-small-hackathon-hearthnet.hf.space","node_id":"hf-space-anchor"}'

# 4. Verify peering
python -m hearthnet.cli call discovery.peers 1 0 '{}'
```

Or use the helper script:
```bash
python scripts/connect_to_hf.py
```

Once peered, your local node can:
- Route LLM queries **from** the HF Space to your local (better) model
- Push community posts that appear in the HF Space UI
- Share blob files across the connection

> **Note:** The HF Space runs on a public server without a static IP for inbound connections.
> Your local node initiates the connection; the HF Space cannot discover you via mDNS.
> Use `discovery.peer.add` or the invite flow to establish the bridge manually.

---

## Security Model

- **Node identity** — Ed25519 key pair generated locally, never leaves the device.
- **Trust levels** — `unknown` → `member` → `trusted` → `anchor`. Capabilities can require a minimum trust level.
- **Capability scoping** — `AuthToken` restricts which capabilities a caller may invoke.
- **Channel encryption** — M23 X25519 ECDH + ChaCha20-Poly1305 for inter-node transport (opt-in, defaults off).
- **Experimental capabilities** — Phase 3 modules are off by default and require explicit opt-in. The bus refuses to register them unless the feature flag is on.
- **No central authority** — there is no HearthNet.com, no certificate authority, no registration server. Trust is established peer-to-peer via invite chains.

---

## Testing

```bash
# Full suite (133 unit + integration tests):
pytest tests/ -q

# Skip slow E2E browser tests:
pytest tests/ -q -k "not e2e"

# Phase 3 experimental module tests only:
pytest tests/test_phase3_experimental.py -v

# Conformance runner (X09):
python -m hearthnet.conformance.runner --output conformance-report/
```

---

*This document is generated from the spec set in `docs/`. For per-module detail see:*
- *Phase 1+2: `00-OVERVIEW.md`, `CAPABILITY_CONTRACT.md`, `modules/M01-*.md` …*
- *Phase 3: `docs/p2_p3/IMPLEMENTATION_REFERENCE_p3.md`, `docs/p2_p3/M26-*.md` …*
