# HearthNet — Technical PRD v2

**Distributed neighbourhood AI mesh**
*Resilient, community-owned local AI infrastructure that survives internet outages.*

---

| | |
|---|---|
| **Status** | Draft v2 — supersedes v1  |
| **Author** | Christof |
| **Target** | Gradio Winter '25 Hackathon submission + post-hackathon product roadmap |
| **License (planned)** | AGPLv3 for the kernel, MIT for clients |
| **Repo (planned)** | github.com/Chris4K/hearthnet |
| **Demo (planned)** | huggingface.co/spaces/Chris4K/hearthnet-demo |

---

## 0. The 2-minute pitch

Imagine the internet cable in your neighbourhood gets cut. Right now, that means no Google, no ChatGPT, no maps, no marketplace, no messaging. The cloud goes silent and you're alone with whatever's on your phone.

HearthNet changes that. It's a local AI mesh that turns the computers already in your neighbourhood — your gaming PC, your neighbour's old laptop, the Raspberry Pi in someone's attic — into a shared, resilient AI cooperative. Discovery is automatic. You don't configure anything. You open the app, it finds the nodes nearby, you ask a question. The answer is generated locally, on someone's GPU, three streets away.

When the internet is up, it federates with the cloud. When the internet drops, you don't even notice — the system switches to local mode, and the AI, the file library, the neighbourhood marketplace, and the local chat all keep working.

The architecture is built around one idea: a **capability bus**. Every node announces what it can do — run inference, store files, hold a vector index, relay messages. Every request finds the best node for the job. New service? Plug it in. New transport — LoRa, mesh radio? Plug it in below. The kernel stays small. The system gets stronger as the community grows.

For the hackathon, we demo the full loop live: a mesh of three real nodes on stage, LLM routing across them, RAG over an emergency PDF library, a community marketplace, and a clean fail-over when we unplug the WAN cable. Phase 2 brings real-distance transports and federated learning across communities. Phase 3 explores actual distributed inference.

The cloud owns AI today. HearthNet is the bet that communities will own it tomorrow.

---

## 1. Executive summary

HearthNet is a peer-to-peer software stack that lets a small number of devices on the same network (or, later, the same neighbourhood) discover each other, share compute and storage, and provide AI services to each other and to thin clients. The system is designed to keep working when the wider internet does not.

The technical core is a **capability bus**: a small, transport-agnostic routing layer that knows which nodes can fulfil which request, picks the best one, enforces a schema contract, handles backpressure, and reports health. Everything else — the LLM, the RAG, the file share, the marketplace, the UI — is a plug-in.

The MVP is a single-binary Python application that runs on Linux, macOS, and Windows, exposes a Gradio web UI on `localhost:7860`, joins a LAN mesh via mDNS, and uses llama.cpp or Ollama for inference. The demo runs on three machines: a workstation with a GPU, a laptop, and a Raspberry Pi acting as a thin client.

Post-hackathon the project has three viable commercial paths: retail-continuity offering, a municipal/civil-defence pilot in NRW, and a "HearthNet-in-a-Box" appliance for community groups.

---

## 2. Vision & positioning

### 2.1 The problem we're solving

Modern households are now utterly dependent on cloud AI. The same is increasingly true for businesses, schools, and emergency services. When the cable, the DSL line, or the cloud provider drops, productivity stops. Communities have no fallback.

At the same time, the average household has multiple idle computers — a gaming PC at 5% utilisation, a workstation that runs Slack, an old laptop in a drawer. Aggregated across a neighbourhood, this is a non-trivial amount of compute. None of it cooperates today.

### 2.2 What HearthNet is

A peer-to-peer, local-first AI fabric that:

- Discovers nodes automatically on the local network
- Routes AI/data requests to the best available node
- Tolerates partitions, internet outages, and node churn
- Federates with the cloud when available, falls back gracefully when not
- Is owned by its participants — no central operator, no telemetry pipeline to a vendor

### 2.3 What HearthNet is not

- Not a replacement for high-end cloud AI on always-online workloads
- Not a competitor to Tor or I2P — anonymity is not a goal
- Not Petals — distributed-tensor inference is an experimental Phase 3 explore, not the core
- Not a blockchain. There are no tokens, no consensus across communities, no incentive design beyond reciprocity
- Not magic. It will not let you run GPT-4-class models on a Raspberry Pi

### 2.4 Differentiation

Most hackathon AI projects today use cloud APIs and are dead the moment the API goes down or runs out of credits. HearthNet's whole point is the opposite: it gets *more* useful as the network gets less reliable.

---

## 3. Goals & non-goals

### 3.1 Primary goals (P0)

- Zero-configuration discovery on a LAN
- Capability-based service routing across nodes
- One real AI service (LLM inference) routed across at least 3 nodes
- One real data service (RAG over a small PDF corpus)
- Persistent local marketplace with offline-tolerant sync
- A clean emergency-mode UX triggered by WAN failure
- A live topology visualisation suitable for stage demo
- Single-binary install on Linux, macOS, Windows

### 3.2 Secondary goals (P1)

- Mobile-friendly client that connects to a host node
- Content-addressed file sharing with chunk-level dedup
- Cross-community federation over the internet when available
- Embedded skill library reuse from existing FORGE work

### 3.3 Stretch goals (P2)

- One experimental Petals-style distributed-layer demo on a small model (1.5B or smaller), as a feature flag
- LoRa beacon for "node alive" pings over distance, no AI traffic
- Translation service for German ↔ English ↔ Plattdeutsch

### 3.4 Explicit non-goals (this release)

- Full distributed-tensor inference for production use
- WireGuard or Tailscale overlay (use plain TLS on LAN)
- Anonymous routing (Tor-style)
- Cryptocurrency, token, or financial-incentive layer
- Sub-millisecond latency for any operation
- Replacing professional emergency-response systems
- Storing personally-identifying data centrally anywhere

---

## 4. The demo loop

The full hackathon demo is one continuous two-minute story, scripted to hit every feature exactly once. Build only what this story needs; everything else is a slide.

### 4.1 Setup on stage

- Three physical machines: workstation with GPU ("**Forge**"), laptop ("**Hearth**"), Raspberry Pi 5 ("**Spark**")
- One travel router with a clearly-visible WAN cable
- All three nodes pre-joined to a community called `niederrhein-demo`
- A pre-loaded RAG corpus: 6 PDFs covering rainwater purification, generator safety, first aid, German civil-defence procedure, and a Sankt-Martin children's song book
- Three pre-populated marketplace posts so the page is not empty on open

### 4.2 The script (~120 seconds)

| t | What happens | What it demonstrates |
|---|---|---|
| 0:00 | Open the Gradio UI on the laptop. Topology shows 3 connected nodes, green | Discovery works |
| 0:10 | Ask: *"Wie reinige ich Regenwasser ohne Strom?"* | LLM + RAG over local PDFs |
| 0:15 | Animated edge from Hearth → Forge → Hearth as the request routes and streams back | Capability routing visible |
| 0:35 | Open marketplace tab, post: *"Suche Wasserkanister, 20L"* | Marketplace + signed events |
| 0:50 | **Yank the WAN cable** | Trigger |
| 0:54 | Banner appears: *"INTERNET OFFLINE — LOKAL AKTIV"*, UI re-skins amber | Emergency mode |
| 1:00 | Same question, different phrasing | Still works, now visibly local |
| 1:20 | Send a chat message to "Frank" (Spark node) — store-and-forward across mesh | Local comms |
| 1:35 | Plug WAN cable back in | Trigger |
| 1:40 | Banner clears, federation event log replays, new cloud-side node appears greying-in | Reconciliation |
| 1:55 | Closing line | — |

### 4.3 Design implications of the demo

- The topology viz must animate request flow, not just node presence
- The emergency banner must trigger in under 5 seconds
- Marketplace posts must be content-addressed and signed so the rejoin merge has something to demonstrate
- The LLM must stream tokens — silence for 10 seconds while a model loads will lose the room
- A "fake mesh" mode is needed for dry runs (and as a fallback if something dies on stage)

---

## 5. System architecture

### 5.1 Layered model

```
┌──────────────────────────────────────────────────────────────┐
│ L5 — Application                                             │
│      Gradio dashboard · topology viz · emergency UX · mobile │
├──────────────────────────────────────────────────────────────┤
│ L4 — Service plane                                           │
│      LLM · RAG · files · marketplace · chat · embeddings     │
├══════════════════════════════════════════════════════════════┤
│ L3 — CAPABILITY BUS  ← the integration point                 │
│      Registry · router · health · schema · backpressure      │
├══════════════════════════════════════════════════════════════┤
│ L2 — Messaging                                               │
│      RPC · pub-sub · streams · content-addressed chunks      │
├──────────────────────────────────────────────────────────────┤
│ L1 — Identity & discovery                                    │
│      Device keys · signed manifests · mDNS · UDP · DHT later │
├──────────────────────────────────────────────────────────────┤
│ L0 — Physical transport                                      │
│      LAN/WiFi · ethernet · hotspot · internet relay · LoRa   │
└──────────────────────────────────────────────────────────────┘
       Trust & federation (signed community manifests) cross-cut L1–L4
       Observability (logs, traces, metrics) cross-cut all layers
```

### 5.2 Loose coupling, in one rule

> No service knows about a transport. No transport knows about a service. Both speak only to the capability bus.

This is the only structural rule that matters. If a feature requires a service to import a transport module, the design is wrong and the feature should be redesigned to register a new capability instead.

### 5.3 Process model

A HearthNet node is **one process** by default. Internally it runs:

- The L1 discovery loop (asyncio task)
- The L2 messaging server (FastAPI on a configurable port, default `:7080`)
- The L3 capability bus
- One or more L4 services as in-process modules registered with the bus
- The L5 Gradio app on a separate port (default `:7860`)

Services *may* run out of process and connect to the bus over local IPC, for sandboxing or because they need a different runtime (e.g. llama.cpp in C++). This is supported but not required for MVP.

### 5.4 Node profiles

| Profile | Hardware | Services it runs | Network role |
|---|---|---|---|
| **Anchor** | GPU workstation, ≥32GB RAM, ≥1TB disk | LLM, RAG, files, marketplace, chat, embeddings | Provider |
| **Hearth** | Laptop, 16GB RAM | RAG, files, marketplace, chat, embeddings | Mixed |
| **Spark** | Raspberry Pi 4/5, mobile, browser | Chat, marketplace UI, file cache | Client |
| **Bridge** | Cloud VM | None inferring, only relay & federation | Relay (Phase 2) |

A node decides its profile at startup based on detected hardware, but the user can override.

---

## 6. Layered specification

### 6.1 L0 — Physical transport

The system runs over whatever IP transport is present. No L0 abstraction is exposed to higher layers beyond "is internet up" and "is LAN up". MVP supports:

- WiFi on the local subnet
- Ethernet
- Mobile hotspot (one node acts as router)
- Internet relay (Phase 2: an HTTPS relay node helps two NAT'd peers reach each other)
- LoRa beacons (Phase 3: one-way "I am alive" pings only, no data)

Heuristics for "is internet up":

1. DNS resolve two unrelated anchors (`1.1.1.1`, `8.8.8.8`)
2. HTTPS HEAD to two unrelated anchors with short timeouts
3. ICMP if available, but never relied on
4. Both must succeed within 3 seconds to count as "up"

The detector runs every 10 seconds when up, every 2 seconds when down (to detect restore quickly).

### 6.2 L1 — Identity & discovery

#### 6.2.1 Device keys

Each node generates an Ed25519 keypair on first run. Stored in `~/.hearthnet/keys/` with `0600` permissions. The private key never leaves the device. The public key is the node's permanent ID.

Display form for humans: first 8 bytes of the public key, base32-encoded, formatted as `XXXX-XXXX-XXXX-XXXX`. Long enough to avoid collisions in a community, short enough to read aloud.

#### 6.2.2 Node manifest

A signed JSON document describing what this node is and what it can do. Re-signed and re-broadcast on any change. Schema in §7.1.

#### 6.2.3 Community manifest

A signed JSON document describing the community: name, root key, members, policies. Signed by the root key (the community founder's device key). New members are added by appending a signed invite event. Schema in §8.3.

#### 6.2.4 Discovery transports

- **mDNS / Zeroconf** — primary, works out of the box on LAN. Service type: `_hearthnet._tcp.local.`
- **UDP broadcast** — secondary, for networks that block mDNS. Multicast group `239.255.42.42:42424`. Payload: a one-line manifest summary
- **DHT (Kademlia)** — Phase 2, for cross-LAN discovery via internet relay
- **LoRa beacon** — Phase 3, for long-distance "this community exists" pings

Discovery flow:

1. Node starts, generates manifest, signs it
2. Broadcasts via all available discovery transports
3. Listens for other manifests
4. For each new node: verify signature against community manifest (if same community), then establish an L2 connection
5. Send a probe RPC: get health, latency, declared capabilities
6. Register the remote capabilities locally with provenance

### 6.3 L2 — Messaging

#### 6.3.1 Wire protocol

Plain HTTP/1.1 over TLS for MVP. Connection per peer, reused. Headers carry capability name, request ID, and signature. Body is JSON (or binary for chunks). Streaming responses use Server-Sent Events.

Phase 2 considers HTTP/3 (QUIC) for better mobile and lossy-link behaviour, especially for streamed token output. The capability bus does not care which is used.

#### 6.3.2 Message types

- **Request/reply** — one-shot RPC, standard pattern
- **Stream** — server-streams a sequence of frames (LLM tokens, file chunks, progress events)
- **Pub-sub** — fire-and-forget event topic with subscription, used for manifest updates and marketplace events
- **Chunk transfer** — bulk binary, content-addressed, may be parallel from multiple sources

#### 6.3.3 Content-addressed storage

Files larger than 64KB are split into 256KB chunks. Each chunk is hashed with BLAKE3. The file is described by a small **manifest** listing chunk CIDs and the merkle root.

Nodes advertise which CIDs they hold. When a node needs a file, it asks the bus for sources by CID, then fetches chunks in parallel.

#### 6.3.4 Backpressure

Every stream has a flow-control window (frames-in-flight). Servers stop sending when the window is full; clients refresh the window with ACK frames. Default window: 16 frames. Token streams use this so a slow client doesn't blow up server memory.

#### 6.3.5 Retries

Idempotent requests retry up to 3 times with exponential backoff. Non-idempotent requests (anything mutating, e.g. marketplace post) carry a client-generated UUID so the server can dedupe.

### 6.4 L3 — Capability bus

This is the part of the system that justifies the whole project. Spec in §11.

### 6.5 L4 — Service plane

Each service is a Python module that implements a small interface:

```python
class Service(Protocol):
    name: str
    version: str
    def capabilities(self) -> list[CapabilityDescriptor]: ...
    async def handle(self, capability: str, payload: dict) -> dict | AsyncIterator[dict]: ...
```

Services in §12.

### 6.6 L5 — Application plane

The Gradio web UI is the primary interface for MVP. Mobile is a thin web client (no native app for hackathon). The dashboard is the only UI surface — there is no separate admin interface. Power users get a CLI (`hearthnet status`, `hearthnet capability list`, etc.).

---

## 7. Capability contract — the key abstraction

This is the most important section. If anything in this PRD is wrong, fix this last. If anything is right, build this first.

### 7.1 Node manifest schema

```json
{
  "version": 1,
  "node_id": "ed25519:7H4G-Y9KL-2P3M-X8QR",
  "display_name": "garage-pc",
  "community_id": "ed25519:NIEDERRHEIN-DEMO-...",
  "profile": "anchor",
  "endpoints": [
    {"transport": "https", "host": "192.168.188.25", "port": 7080}
  ],
  "hardware": {
    "gpu": "RTX 5090",
    "vram_gb": 32,
    "ram_gb": 128,
    "cpu_cores": 24,
    "disk_free_gb": 4000
  },
  "capabilities": [
    {
      "name": "llm.chat",
      "version": "1.0",
      "params": {
        "model": "qwen2.5-7b-instruct",
        "quant": "q4_k_m",
        "ctx": 8192,
        "modality": ["text"]
      },
      "schema_hash": "blake3:..."
    },
    {
      "name": "rag.query",
      "version": "1.0",
      "params": {"corpus": "niederrhein-emergency", "k_max": 20},
      "schema_hash": "blake3:..."
    }
  ],
  "uptime_seconds": 43210,
  "load": {"cpu": 0.12, "vram_used_gb": 6.4},
  "issued_at": "2026-05-26T08:14:22Z",
  "expires_at": "2026-05-26T08:14:52Z",
  "signature": "ed25519:..."
}
```

Notes:

- Manifests **expire** in 30 seconds. A node re-broadcasts before expiry. This is the heartbeat.
- `schema_hash` is the hash of the request/response JSON schema for that capability. Two nodes with the same hash speak the exact same contract.
- `load` is advisory; the router uses it to pick under-loaded nodes.

### 7.2 Capability descriptor schema

```json
{
  "name": "llm.chat",
  "version": "1.0",
  "stability": "stable",
  "request_schema": { /* JSON Schema */ },
  "response_schema": { /* JSON Schema */ },
  "stream": true,
  "params": {
    "model": "qwen2.5-7b-instruct",
    "quant": "q4_k_m",
    "ctx": 8192
  },
  "guarantees": {
    "max_latency_ms_p50": 1200,
    "max_concurrent": 4
  }
}
```

`name` is a dotted namespace (`llm.*`, `rag.*`, `file.*`, `market.*`, `chat.*`, `embed.*`, `ocr.*`, `tts.*`, `stt.*`, `trans.*`).

`version` is semver, but only major.minor — patch is irrelevant on the wire.

`stability` is `experimental`, `beta`, or `stable`. Clients can filter.

### 7.3 Wire format — request

```http
POST /bus/v1/call HTTP/1.1
Host: 192.168.188.25:7080
Content-Type: application/json
X-HearthNet-Capability: llm.chat
X-HearthNet-Capability-Version: 1.0
X-HearthNet-Request-Id: 01HXR8...
X-HearthNet-From: ed25519:CLIENT-NODE-ID
X-HearthNet-Signature: ed25519:...
Accept: application/json, text/event-stream

{
  "params": {"model": "qwen2.5-7b-instruct", "ctx": 8192},
  "input": {
    "messages": [
      {"role": "user", "content": "Wie reinige ich Regenwasser ohne Strom?"}
    ],
    "max_tokens": 512,
    "temperature": 0.7
  }
}
```

### 7.4 Wire format — non-stream response

```http
HTTP/1.1 200 OK
Content-Type: application/json
X-HearthNet-Request-Id: 01HXR8...
X-HearthNet-From: ed25519:SERVER-NODE-ID
X-HearthNet-Signature: ed25519:...

{
  "output": {
    "message": {"role": "assistant", "content": "..."}
  },
  "meta": {
    "tokens_in": 42,
    "tokens_out": 178,
    "ms": 1834,
    "model": "qwen2.5-7b-instruct"
  }
}
```

### 7.5 Wire format — stream response

```http
HTTP/1.1 200 OK
Content-Type: text/event-stream
X-HearthNet-Request-Id: 01HXR8...
X-HearthNet-From: ed25519:SERVER-NODE-ID

event: token
data: {"text":"Sie"}

event: token
data: {"text":" können"}

event: token
data: {"text":" Regenwasser"}

event: done
data: {"tokens_out":3,"ms":380,"signature":"ed25519:..."}
```

### 7.6 Wire format — error

```http
HTTP/1.1 503 Service Unavailable
X-HearthNet-Request-Id: 01HXR8...

{
  "error": "capacity_exceeded",
  "retry_after_ms": 2000,
  "alt_capabilities": ["llm.chat@0.9"],
  "alt_nodes": ["ed25519:OTHER-ANCHOR-NODE-ID"]
}
```

Error codes are a closed set: `not_found`, `capacity_exceeded`, `schema_mismatch`, `unauthorized`, `revoked`, `internal_error`, `not_implemented`, `timeout`, `partition`.

### 7.7 Versioning rules

- Major version bump → breaking change. Old clients must be rejected with `schema_mismatch`.
- Minor version bump → additive. Old clients still work, new fields are optional.
- Two nodes match on capability if `name` matches and `version` major is equal and the requested version minor ≤ offered version minor.
- `schema_hash` is computed from the canonical (sorted-key, no-whitespace) JSON of the request+response schemas. Two nodes with identical hashes can call each other with zero coordination.

### 7.8 Capability discovery flow

1. Client wants to do `llm.chat`
2. Asks local bus: "who offers `llm.chat@>=1.0`?"
3. Bus returns a ranked list of remote nodes that meet the criteria
4. Client picks the top one (or the bus does — see §11)
5. Client sends the request with the chosen node's signature requirement
6. Server validates, executes, replies (or streams)
7. Bus records latency, success/failure, updates ranking

---

## 8. Identity, trust & federation

### 8.1 Trust model in one paragraph

Trust is **community-scoped**. A community has a root key (the founder's device key). Members are added by signed invite events. To join, a new device generates a key, presents its public key to an existing member (in person, via QR code), and receives a signed invite. The invite is a signed event appended to the community log. The new device is now a member. All capability calls within the community are signed; signatures are checked against the community member list.

There are no certificate authorities, no PKI, no chains of trust. This is good enough for a neighbourhood. It is not good enough for the whole internet, and that is fine.

### 8.2 Trust levels

| Level | Meaning | Who can be this |
|---|---|---|
| `unknown` | Just discovered, not in any community | Random discoverable nodes |
| `member` | Signed in to this community | Default for invited devices |
| `trusted` | Marked by 3+ members as trusted | Used for risky capabilities (file delete, federation gateway) |
| `anchor` | Marked by the root key as infrastructure | Always-on, primary providers |

A node's level changes via signed events. Demoting needs more signatures than promoting (3 to demote a `trusted`, 1 to promote to `trusted`).

### 8.3 Community manifest schema

```json
{
  "version": 1,
  "community_id": "ed25519:...",
  "name": "Niederrhein Demo",
  "root_key": "ed25519:...",
  "created_at": "2026-05-26T08:00:00Z",
  "policy": {
    "min_signatures_to_invite": 1,
    "min_signatures_to_demote": 3,
    "capability_token_ttl_seconds": 86400,
    "federation_enabled": true
  },
  "members": [
    {"node_id": "ed25519:...", "level": "anchor", "added_at": "..."},
    {"node_id": "ed25519:...", "level": "member", "added_at": "..."}
  ],
  "signature": "ed25519:..."
}
```

The manifest is the result of replaying the community event log; it is materialised so new nodes don't have to replay everything to join.

### 8.4 Capability tokens

Optional layer for fine-grained delegation. A node can issue a short-lived token allowing a specific other node to make a specific capability call. Used in Phase 2 for federation across communities: community A's anchor signs a token allowing community B's anchor to query its RAG. MVP does not use tokens; signing is per-request.

### 8.5 Revocation

To revoke a member, three other members publish a signed `revoke` event. The community manifest is regenerated. All other nodes update their local copy and refuse to honour signatures from the revoked node going forward.

There is no online revocation list. The community manifest itself is the revocation mechanism.

### 8.6 Federation between communities (Phase 2)

Two communities pair when their root keys cross-sign a federation manifest. Federation grants specific capabilities (e.g. "you may query our RAG, but not our marketplace"). Federated calls travel via a Bridge node or a public relay.

### 8.7 Threat model (MVP)

In scope:

- **Drop-in node**: a random LAN device tries to join; rejected, not a member
- **Stale manifest replay**: old signed manifest re-broadcast; rejected by expiry
- **Single member compromised**: can act as themselves but cannot promote others without colluders; revocable
- **Network observer**: sees who talks to whom; we accept this (no anonymity goal)

Out of scope:

- **Root key compromised**: catastrophic; community must regenerate
- **Sybil at community level**: not protected against — communities are trust roots, not Sybil-resistant
- **Side-channel attacks**: not protected against on shared hardware
- **Malicious model output**: not protected against; this is a content policy problem, not a protocol one

---

## 9. Discovery in detail

### 9.1 mDNS service definition

```
Service type:  _hearthnet._tcp.local.
Instance name: <display_name>-<short_node_id>
Port:          7080
TXT records:
  v=1
  node=<short_node_id>
  community=<short_community_id>
  profile=anchor|hearth|spark|bridge
  caps=llm.chat,rag.query,file.read,...
  manifest_url=https://<host>:<port>/manifest
```

`caps` lists capability names only. Full descriptors are fetched via `manifest_url`.

### 9.2 UDP broadcast format

Plain JSON line, ≤ 1KB, on `239.255.42.42:42424`:

```json
{"v":1,"node":"short_id","community":"short_id","port":7080,"caps":["llm.chat","rag.query"]}
```

Rate: every 5 seconds when discovering, every 30 seconds when stable.

### 9.3 Internet-relay discovery (Phase 2)

A small relay node accepts manifest registrations from communities and serves a "members of community X seen recently" query. Used to bootstrap cross-LAN federation. Anyone can run a relay; communities decide which to trust.

### 9.4 LoRa beacon (Phase 3)

868MHz (EU) or 915MHz (US), short payload: `<community_short_id, node_short_id, seq>`. One way, no AI traffic. Purpose: a phone with a LoRa module knows a HearthNet community exists in range, even with no WiFi.

### 9.5 First-run UX

The first time a user runs HearthNet:

1. Generate device key (silent)
2. Ask: *Create a new community or join existing?*
3. If create: prompt for community name, sign founding manifest. Show a QR code with the community ID and invite policy.
4. If join: prompt for QR scan or invite link. Acquire signed invite from an existing member (in person, via the app). Now a member.

Total time to first useful state: under 60 seconds.

---

## 10. Messaging & transport detail

### 10.1 Connection lifecycle

- Peer discovered via L1
- Bus initiates TLS handshake (self-signed cert, pinned to the node's key on first contact)
- Subsequent connections re-use the pinned cert; mismatch = refused + log
- Idle connections close after 60 seconds
- Failed reconnect uses exponential backoff capped at 30 seconds

### 10.2 Streaming protocol details

LLM token streams use SSE for simplicity (works in browsers, easy to debug, fits HTTP/2). Per-frame format:

```
event: token
data: {"text":"...", "logprobs":[...], "stop":false}

event: token
data: {"text":"...", "stop":false}

event: done
data: {"tokens_out":N, "stop_reason":"end", "ms":M}
```

Clients close the connection to cancel. Servers respect cancellation within 200ms.

### 10.3 Chunk transfer

A file with CID `blake3:abc...` is described by a manifest:

```json
{
  "cid": "blake3:abc...",
  "size": 4824711,
  "chunk_size": 262144,
  "chunks": [
    {"i": 0, "cid": "blake3:..."},
    {"i": 1, "cid": "blake3:..."}
  ]
}
```

A client wanting the file:

1. Asks the bus: who has `blake3:abc...`?
2. Gets a list of source nodes
3. For each chunk, picks a source (round-robin or load-aware), requests it
4. Verifies the chunk hash before accepting
5. Reassembles when all chunks received

This is BitTorrent-lite. About 300 lines of Python. Provides dedup, integrity, and parallel transfer for free.

### 10.4 Pub-sub topics

| Topic | Producer | Consumer | Payload |
|---|---|---|---|
| `community.member.added` | Any member with invite right | All members | Signed invite event |
| `community.member.revoked` | 3 members | All members | Signed revoke event |
| `node.manifest.updated` | Each node | All members | Updated node manifest |
| `marketplace.post.created` | Posting member | All members | Signed marketplace event |
| `marketplace.post.expired` | Original poster or auto | All members | Signed expiry event |
| `chat.message.<recipient>` | Sending member | Recipient | Signed chat message |
| `emergency.mode.changed` | Each node locally | UI only | `{"online": bool, "since": "..."}` |
| `federation.peer.added` | Anchor with federation right | All anchors | Signed federation event |

All events are signed. All have a Lamport timestamp. All can be replayed.

### 10.5 Backpressure detail

Each stream has:

- `window_size`: max frames in flight (default 16)
- `frames_sent`: count
- `frames_acked`: count
- When `frames_sent - frames_acked >= window_size`, sender pauses

ACK frame:

```
event: ack
data: {"upto": 42}
```

Client sends ACKs every 8 frames received (half-window). If 5 seconds pass with no ACK, sender treats stream as broken.

---

## 11. Capability bus internals

### 11.1 Data structures

```python
class CapabilityEntry:
    node_id: str
    capability: str          # "llm.chat"
    version: tuple[int,int]  # (1, 0)
    schema_hash: str
    params: dict
    last_seen: float
    p50_latency_ms: float
    p99_latency_ms: float
    success_rate: float      # rolling 100 calls
    in_flight: int
    declared_max_concurrent: int
```

The bus keeps one of these per (node, capability) pair.

### 11.2 Routing algorithm

When a local service or client requests capability `C@V`:

```python
def route(capability: str, version_req: VersionReq, params: dict) -> CapabilityEntry | None:
    candidates = [
        e for e in registry
        if e.capability == capability
        and version_compatible(e.version, version_req)
        and params_compatible(e.params, params)
        and e.last_seen > now() - 60
        and e.in_flight < e.declared_max_concurrent
    ]
    if not candidates:
        return None
    # Score: lower is better
    def score(e):
        latency = e.p50_latency_ms
        load = e.in_flight / max(e.declared_max_concurrent, 1)
        reliability_penalty = (1 - e.success_rate) * 1000
        return latency * (1 + load) + reliability_penalty
    return min(candidates, key=score)
```

`params_compatible` is capability-specific. For `llm.chat`, the model name and minimum context length must match. For `rag.query`, the corpus name must match.

### 11.3 Local vs remote

If the local node also offers the capability, prefer local unless local load exceeds a threshold (default 80% of `declared_max_concurrent`). This biases toward local execution which is faster and avoids network for offline mode.

### 11.4 Sticky routing

For multi-turn capabilities (chat continuations referencing a prior conversation), the bus keeps a session → node binding for the conversation duration. Default TTL: 10 minutes idle.

### 11.5 Health tracking

After each call, record:

- success / fail
- latency
- response size

Ideally uses gradio trackio https://github.com/gradio-app/trackio
Rolling window of last 100 calls per (node, capability). Old entries decayed. A node with success rate < 0.5 over the last 20 calls is **quarantined** (skipped for 60 seconds, then probed).

### 11.6 Schema enforcement

Both sides validate against the JSON schema declared in the capability descriptor. Reject mismatches with `schema_mismatch` and the expected `schema_hash`. This is the contract.

### 11.7 Backpressure at the bus level

The bus has a max in-flight per (capability, node) pair. When saturated, new requests either:

- Queue with a configurable timeout, or
- Get rejected with `capacity_exceeded` and an `alt_nodes` list

MVP: queue with 1s timeout, then reject.

### 11.8 Observability hooks

Every call emits a trace event:

```json
{
  "ts": "2026-05-26T08:14:33.281Z",
  "trace_id": "01HXR8...",
  "capability": "llm.chat",
  "from": "node_short_id_A",
  "to": "node_short_id_B",
  "version": "1.0",
  "result": "ok",
  "ms": 1234,
  "tokens_in": 42,
  "tokens_out": 178
}
```

Traces go to a local SQLite ring buffer. Optionally exported to OpenTelemetry in Phase 2.

---

## 12. Services

### 12.1 LLM inference service (`llm.*`)

#### Capabilities

- `llm.chat@1.0` — multi-turn chat
- `llm.complete@1.0` — single-shot completion
- `llm.embed@1.0` — text embeddings (often a separate model)
- `llm.classify@1.0` — zero-shot classification (Phase 2)

#### Backends

- llama.cpp server (primary)
- Ollama (drop-in)
- vLLM (Phase 2, for batched throughput on the anchor)
- LM Studio (Christof's existing setup at `192.168.188.25:1234`)
- HF Inference API (when internet is up, as another route the bus may pick)
- Anthropic / OpenAI / others (Phase 2, with user-supplied keys)

The adapter pattern:

```python
class LlmBackend(Protocol):
    name: str
    async def chat(self, messages, **params) -> AsyncIterator[Token]: ...
    async def embed(self, texts) -> list[list[float]]: ...
```

The service module registers one capability per backend × model × quant combination, so the bus sees `llm.chat:qwen2.5-7b@q4`, `llm.chat:qwen2.5-7b@q8`, `llm.chat:gemma-3-9b@q4` as separate things.

#### MVP models

- `qwen2.5-7b-instruct@q4_k_m` (anchor) — primary chat
- `qwen2.5-1.5b-instruct@q4` (hearth) — fallback when anchor busy
- BGE-small embedding model (anchor + hearth) — RAG
- Christof's existing Proto-Cognitive Architecture v5.2 model as an experimental third option (HybridLLM with PinnedEpisodicStore)

#### Resource control

- Each backend declares `max_concurrent` based on VRAM
- Bus respects this hard limit
- Long requests can be **cancelled** mid-generation by closing the stream

### 12.2 RAG service (`rag.*`)

#### Capabilities

- `rag.query@1.0` — query a corpus, return chunks with scores
- `rag.ingest@1.0` — add a document to a corpus (member-only)
- `rag.list_corpora@1.0` — list local corpora

#### Storage

- ChromaDB for vectors (local file-based)
- Documents stored as content-addressed blobs (§10.3)
- One Chroma collection per corpus

#### Corpora

- `niederrhein-emergency` — the demo corpus (6 emergency PDFs)
- `community-knowledge` — user-contributed
- `personal` — per-user, not shared

#### Query flow

1. Embed query (via local `llm.embed` capability, routed by bus)
2. Search Chroma top-K
3. Return chunks with metadata: source doc CID, page, score
4. Caller passes chunks as LLM context

#### Ingest flow

1. Member uploads PDF via UI
2. PDF parsed (PyPDF2 → text + page numbers)
3. Chunked (1000 tokens, 200 overlap)
4. Each chunk embedded
5. Stored in Chroma with metadata
6. Original PDF stored as CID blob, advertised on the chunk service
7. `marketplace.knowledge.added` event published

### 12.3 File / chunk service (`file.*`)

#### Capabilities

- `file.read@1.0` — fetch a chunk by CID
- `file.list@1.0` — list locally-held CIDs
- `file.advertise@1.0` — claim to hold a CID (Phase 2: gossip)
- `file.put@1.0` — accept a chunk (member-only, opt-in)

#### Storage layout

```
~/.hearthnet/blobs/
  <first2bytes>/<rest of CID>.bin
```

Sharded for filesystem performance.

#### Garbage collection

- Default LRU eviction at 80% disk capacity threshold
- "Pinned" CIDs (user-marked) never evicted
- Marketplace event log + community manifest are always pinned

### 12.4 Marketplace service (`market.*`)

#### Capabilities

- `market.list@1.0` — list current posts
- `market.post@1.0` — create a post (signed)
- `market.expire@1.0` — mark expired (signed by original poster or after TTL)
- `market.search@1.0` — semantic search using embeddings

#### Data model

A post is an **event**:

```json
{
  "event_type": "market.post.created",
  "event_id": "01HXR8...",
  "lamport": 4218,
  "wall_clock": "2026-05-26T08:14:22Z",
  "author": "ed25519:NODE-ID",
  "community": "ed25519:COMMUNITY-ID",
  "data": {
    "category": "offer|request|info|emergency",
    "title": "Suche Wasserkanister, 20L",
    "body": "...",
    "location": {"lat": 51.5, "lng": 6.2, "label": "Issum"},
    "ttl_seconds": 86400,
    "tags": ["wasser","notfall"]
  },
  "signature": "ed25519:..."
}
```

This is EBKH-shaped on purpose. Reuse the event sourcing patterns Christof already built.

#### Sync semantics

Append-only log. Lamport timestamps for ordering. CRDT-style merge on rejoin: replay events in Lamport order, dedupe by `event_id`. Last-writer-wins on conflicting updates to the same post (rare, since posts are mostly create+expire).

### 12.5 Chat service (`chat.*`)

#### Capabilities

- `chat.send@1.0` — send a direct message (signed)
- `chat.history@1.0` — local history retrieval
- `chat.thread@1.0` — group conversation (Phase 2)

#### Delivery

- Direct messages are signed, addressed by recipient node ID
- If recipient is online, deliver directly
- If recipient is offline, **store-and-forward**: encrypted blob held by 2 randomly-chosen anchor nodes, delivered when recipient reconnects
- Read receipts are signed events

#### Encryption

MVP: TLS at transport, signed at app layer, no end-to-end encryption between users. Acceptable inside a trusted community.

Phase 2: optional E2E using X25519 + ChaCha20Poly1305. Signal-style ratchet deferred to Phase 3.

### 12.6 Embedding service (`embed.*`)

Separated from `llm.*` because embeddings have different scaling characteristics (small model, high throughput, often batch).

Capabilities:

- `embed.text@1.0` — embed a list of strings
- `embed.image@1.0` — embed an image (Phase 2, CLIP)

### 12.7 OCR service (Phase 2, `ocr.*`)

For ingesting scanned PDFs and photos of documents (emergency notices on lampposts, hand-written notes).

Backends: Tesseract for MVP, TrOCR for handwriting.

### 12.8 Translation service (Phase 2, `trans.*`)

German ↔ English ↔ Plattdeutsch (the Niederrhein angle).

Backends: NLLB for general, optional fine-tune for Plattdeutsch (likely a Christof project).

### 12.9 Speech services (Phase 2, `tts.*` `stt.*`)

- Whisper for STT
- Edge-TTS or XTTS-v2 for TTS (Christof already has the XTTS pipeline from his podcast generator)

### 12.10 Image services (Phase 2, `img.*`)

- Florence-2 for captioning (Christof's pipeline)
- FLUX.1-dev LoRA for generation (Christof's pipeline)
- Particularly useful for "describe this damage photo" emergency use cases

---

## 13. Emergency mode

### 13.1 Detection

A small daemon runs in every node. Every 10 seconds when believed-online, every 2 seconds when believed-offline.

Probes:

1. DNS resolve `cloudflare.com` and `quad9.net`
2. HTTPS HEAD `https://1.1.1.1/cdn-cgi/trace` and `https://www.google.com/generate_204`
3. All four with 2-second timeouts
4. Online = ≥3 of 4 succeed

State machine:

- `ONLINE` → `DEGRADED` (one probe failed) → `OFFLINE` (≥2 failed for 30s)
- `OFFLINE` → `ONLINE` directly when all 4 succeed for 10s

Each transition publishes `emergency.mode.changed` locally.

### 13.2 UX changes when offline

- Top banner: `INTERNET OFFLINE — LOKAL AKTIV` (amber)
- Topology graph collapses to local nodes only (cloud-side bridges go grey)
- Cloud-routed LLM backends (HF API, Anthropic) drop out of the capability registry
- Marketplace shows a "Notfall-Modus" filter prominent
- A new tab appears: **Notfall** — direct links to the emergency PDF corpus, neighbour list with last-seen times, generator/water/light shared resources
- Chat switches to store-and-forward UI

### 13.3 Behavioural changes when offline

- LLM router prefers local-only models
- File transfers stop seeking internet-hosted sources
- Federation pause (peer communities cannot be reached)
- Discovery rate increases (UDP broadcasts more often, to find newly-arrived neighbours faster)

### 13.4 Restore behaviour

When internet returns:

1. Banner clears
2. Re-register cloud capabilities
3. Replay any queued federation events to peer communities
4. Resync marketplace event log with bridge nodes if any
5. Send queued chat messages
6. Optional: notify the user of how many events synced

### 13.5 Anti-flapping

If transitions occur more than 3 times in 60 seconds, system stays in the more pessimistic state for the rest of that window. Prevents banner flicker.

---

## 14. Reconciliation & sync

### 14.1 The event log

Every community has a single conceptual append-only log. In practice it lives as a SQLite database per node, plus a CID-addressed snapshot file recreated nightly.

Schema (simplified):

```sql
CREATE TABLE events (
  event_id TEXT PRIMARY KEY,    -- ULID
  lamport INTEGER NOT NULL,
  wall_clock TEXT NOT NULL,
  community_id TEXT NOT NULL,
  author_node TEXT NOT NULL,
  event_type TEXT NOT NULL,
  data JSON NOT NULL,
  signature TEXT NOT NULL,
  received_at TEXT NOT NULL
);
CREATE INDEX idx_events_lamport ON events(community_id, lamport);
CREATE INDEX idx_events_type ON events(community_id, event_type, lamport);
```

### 14.2 Materialised views

Reading the raw log every time is slow. Each node maintains materialised views:

- `community_manifest` (current member list)
- `marketplace_current` (un-expired posts)
- `chat_history_per_peer`
- `node_health_snapshot`

Views are rebuilt by replaying events from the last snapshot.

### 14.3 Lamport clocks

Each node maintains a Lamport counter. Every event written or received bumps it:

```python
def receive(event):
    lamport = max(self.lamport, event.lamport) + 1
    store(event)
```

### 14.4 Sync protocol

When node A meets node B:

1. A asks B: "what is your highest Lamport per (community, event_type)?"
2. B responds with a vector
3. A computes the delta and sends its missing events
4. B does the same in the other direction
5. Both verify signatures, store events, update materialised views

This is gossip-based, eventually consistent, and resilient to partition.

### 14.5 Conflict resolution

- **Marketplace post update** (e.g. price change): last-writer-wins by Lamport timestamp
- **Member revoke vs. member action**: revoke wins if Lamport(revoke) < Lamport(action); otherwise the action is honoured
- **Two communities with same name**: not a conflict — communities are identified by root key, not by name

### 14.6 Snapshot & compaction

Once per night, each node:

1. Computes the materialised state at `lamport = current_max - 1000`
2. Writes it as a signed snapshot blob (CID-addressed)
3. Marks events below that Lamport as "snapshot-covered"
4. Optionally garbage-collects old events (configurable; default keeps 30 days)

New joiners fetch the latest snapshot + recent events, instead of replaying from genesis.

---

## 15. Application plane

### 15.1 UI surfaces

| Surface | Tech | Purpose |
|---|---|---|
| Gradio dashboard | Gradio 6.0.0 | Primary local-host UI |
| Topology viz | Cytoscape.js inside Gradio | Live mesh state with request animation |
| Chat tab | Gradio chat component | Per-peer conversation |
| Files tab | Gradio file explorer | Browse + upload CID blobs |
| Marketplace tab | Gradio dataframe | Filter, post, search |
| Emergency tab | Bespoke layout | Visible only when offline; large buttons |
| CLI | Click | `hearthnet status`, `hearthnet caps`, `hearthnet log` |
| Mobile web | Vanilla HTML + JS | Lightweight, served from any anchor |

### 15.2 Topology visualisation requirements

- Real-time node list with online/offline indicators
- Animated request flow along edges when a call is in flight
- Color codes capability per edge (LLM = teal, RAG = purple, file = amber, chat = blue)
- Node tooltip shows capabilities, load, latency
- Click a node → opens its public manifest in a side panel
- Edge thickness scales with recent traffic

This is the single visual element judges remember. Build it early.

### 15.3 Mobile client (lightweight)

A static HTML+JS file served from any anchor at `/mobile`. Communicates with the host node via the same bus API. No installation; bookmark to home screen.

Features for MVP: chat, marketplace browse, emergency mode banner, ask-a-question (LLM passthrough). No topology viz on mobile.

### 15.4 First-time install UX

1. `pip install hearthnet` (or download single binary)
2. `hearthnet init` — generates keys, asks for community
3. `hearthnet run` — starts the node
4. Browser opens to `http://localhost:7860`
5. If joining an existing community, displays a "scan invite QR" screen
6. If creating, displays the new community QR code for others to scan

Total time: under 2 minutes from download to first message.

---

## 16. Data model summary

### 16.1 Event types (canonical list)

| Type | Producer | Consumer |
|---|---|---|
| `community.created` | Founder | All |
| `community.member.invited` | Member with right | All |
| `community.member.joined` | Joining device | All |
| `community.member.revoked` | 3 members | All |
| `community.policy.updated` | Root key | All |
| `node.manifest.updated` | Each node | All |
| `capability.registered` | Each node | Local bus only |
| `capability.deregistered` | Each node | Local bus only |
| `market.post.created` | Member | All |
| `market.post.updated` | Author | All |
| `market.post.expired` | Author or auto | All |
| `chat.message.sent` | Sender | Recipient |
| `chat.message.delivered` | Recipient | Sender |
| `chat.message.read` | Recipient | Sender (optional) |
| `file.cid.advertised` | Holder | Local bus, then gossip |
| `file.cid.unpinned` | Holder | Local bus |
| `rag.document.ingested` | Ingester | All members |
| `federation.peer.added` | Anchor | All anchors |
| `federation.peer.removed` | Anchor | All anchors |
| `emergency.mode.changed` | Each node locally | UI only, not in log |

### 16.2 Schema versioning

Every event has a `schema_version`. Old events are kept verbatim; new readers translate via a versioned schema registry. Never rewrite history.

### 16.3 Storage locations

```
~/.hearthnet/
  keys/
    device.ed25519                  (private, 0600)
    device.pub
  communities/
    <community_id>/
      manifest.json                  (latest signed materialised manifest)
      events.sqlite                  (event log)
      snapshots/<lamport>.bin        (signed snapshots)
  blobs/<aa>/<bb...>                 (CID-addressed)
  config.toml
  logs/<date>.log
```

---

## 17. Security

### 17.1 Cryptographic primitives

- **Identity**: Ed25519 (signatures)
- **Key agreement** (Phase 2 E2E): X25519
- **Symmetric** (Phase 2 E2E): ChaCha20-Poly1305
- **Hashing**: BLAKE3 for CIDs, SHA-256 for compatibility where needed
- **TLS**: rustls or Python `ssl` defaults, TLS 1.3 only

### 17.2 Signature scopes

Every:

- Node manifest
- Capability descriptor (signed as part of the node manifest)
- Marketplace event
- Chat message
- Community manifest (root-signed)

is signed. Signature verification is **mandatory** on receipt. Unsigned or invalid events are dropped without log spam (single counter increment).

### 17.3 Sandboxing

User-uploaded content (PDFs, images) is processed in subprocess workers with `nice`-restricted resource limits. No `exec` of user-provided data. No URL fetching from user input without explicit allowlist.

### 17.4 Rate limiting

Per (peer, capability):

- 10 RPS soft limit (responds with `capacity_exceeded`)
- 100 RPS hard limit (drops with no response)

Per (peer, all capabilities):

- 100 RPS soft, 1000 RPS hard

### 17.5 GDPR considerations

This is a Christof project. GDPR-correct from day one is a requirement.

- All personal data (chat, marketplace) is local-first. No central server holds it.
- Users can run `hearthnet erase` to wipe their event participation (best-effort: their signed events still exist on other nodes, but their device key is destroyed, so they cannot be linked back to a person).
- A `personal` corpus in RAG never leaves the device.
- Deletion of marketplace posts: a `market.post.expired` event with `reason: "user_request"` is published; consuming nodes hide the original.
- Right to data export: `hearthnet export` produces a zip of all local data signed by the user.


---

## 18. Observability

### 18.1 Logging

Structured JSON to `~/.hearthnet/logs/<date>.log`. Levels: `debug`, `info`, `warn`, `error`. Default `info`. Log rotation daily, retention 14 days.

### 18.2 Metrics

Prometheus-format scrape endpoint at `:7080/metrics`:

- `hearthnet_requests_total{capability, result}`
- `hearthnet_request_duration_ms{capability, quantile}`
- `hearthnet_nodes_online{community}`
- `hearthnet_event_log_size{community}`
- `hearthnet_emergency_mode{state}`
- `hearthnet_blob_storage_bytes`
- `hearthnet_llm_tokens_generated_total{model}`

### 18.3 Tracing

Every bus call gets a trace ID. Traces are stored locally in SQLite (ring buffer, 10k events). Optional OTLP export in Phase 2.

### 18.4 Health endpoints

- `GET /health` — 200 if process alive
- `GET /ready` — 200 if at least one peer discovered AND at least one capability registered
- `GET /metrics` — Prometheus

### 18.5 Self-diagnostics

`hearthnet doctor` runs a battery of checks:

- mDNS reachable?
- TLS cert valid?
- Discovery sending and receiving?
- At least one peer visible?
- Local services registered?
- Disk space healthy?
- Recent error rate?

Returns a coloured report and a non-zero exit code on failure. Drop-in for CI and on-stage troubleshooting.

---

## 19. Testing strategy

### 19.1 Unit

Every service has unit tests for its capability handlers using a `FakeBus`. Coverage target: 70% on services, 90% on bus.

### 19.2 Integration

A test harness spins up 3 in-process nodes on different ports in the same Python process, with mocked discovery. Integration tests cover:

- Discovery → manifest exchange → first call
- LLM routing prefers low-latency node
- Marketplace event syncs after re-connection
- File transfer with one chunk source going offline mid-stream
- Schema mismatch rejection
- Capability quarantine after failures

### 19.3 Chaos

Three real OS-level processes on the same machine, with `tc` (Linux traffic control) introducing latency, packet loss, and partitions. Scenarios:

- Anchor reboots mid-RAG-query
- 70% packet loss for 30 seconds
- Network partition where 1 node sees 2 others see each other but not it
- Clock skew of ±60 seconds between nodes

### 19.4 Demo dry-runs

Daily in the week before the demo, run the full 2-minute script end to end. Record. Watch for the dead-air moments (model loading, mDNS delay, banner appearance latency). Fix.

### 19.5 Adversarial

- Send malformed manifests
- Send manifests signed by a non-member key
- Send replayed (old) events
- Send oversized payloads
- Send valid signatures from a revoked member

All must fail closed with no leak and no crash.

---

## 20. Hackathon MVP scope

### 20.1 Modules and effort

| ID | Module | Effort (evening hours) | Reuse from existing work |
|---|---|---|---|
| M1 | Node identity & manifest | 4–6 | — |
| M2 | Discovery (mDNS + UDP) | 4–6 | — |
| M3 | Capability bus | 8–12 | NEXUS gateway patterns |
| M4 | LLM inference service | 4–6 | LM Studio at 192.168.188.25, FORGE |
| M5 | RAG service | 6–8 | Christof's existing RAG pipelines |
| M6 | Marketplace service | 4–6 | EBKH event-sourcing patterns |
| M7 | File/chunk service | 6–10 | — |
| M8 | Gradio dashboard + topology viz | 12–16 | FORGE Spaces patterns |
| M9 | Emergency-mode detector | 2–3 | — |
| M10 | Chat service | 4–6 | — |
| M11 | Embedding service | 2–3 | sentence-transformers, existing |
| M12 | CLI (`hearthnet status`, etc.) | 2–4 | — |
| M13 | First-run UX + invite QR | 3–5 | — |
| **Total** | | **61–91h** | |

### 20.2 Build order (demo-driven)

1. **M1 + M2** (identity + discovery) — first because nothing works without them
2. **M3** (bus) with a fake echo service — proves the contract
3. **M4** (LLM) plugged in — first real value
4. **M8** (UI shell + topology viz) — connected to bus, shows mocked nodes initially, then real
5. **M5** (RAG) — demo value
6. **M9** (emergency detector) — wire the banner
7. **M6** (marketplace) — reuses EBKH
8. **M10** (chat) — store-and-forward as bonus
9. **M7** (file/chunk) — last; if cut, files just upload to one node
10. **M11–M13** as time allows

### 20.3 Risk-driven cuts (if behind schedule)

In order of "cut first":

1. **M7 file/chunk** — keep file upload but single-node only
2. **M10 chat** — show in slides only
3. **M13 first-run UX** — judges don't need to install
4. **M12 CLI** — UI is enough
5. **M11 embeddings as separate service** — fold into M5

Never cut: M1, M2, M3, M4, M5, M8, M9.

### 20.4 Definition of done for the demo

- [ ] Three real nodes auto-discover each other on the demo LAN
- [ ] One full LLM query completes with visible token streaming and visible routing
- [ ] One RAG-grounded answer with source citation
- [ ] Two marketplace posts visible across all three nodes
- [ ] WAN-cable unplug triggers the offline banner in ≤5s
- [ ] One question answered while offline using local-only capabilities
- [ ] WAN restore triggers reconciliation visibly
- [ ] Topology viz updates in real time throughout

---

## 21. Out of scope for hackathon

The following are mentioned in the design but **not implemented in MVP**. They are designed-in (no future rewrite needed), just not built yet.

- WireGuard / Tailscale overlay
- LoRa or BLE transports
- DHT-based cross-LAN discovery
- Petals-style distributed-tensor inference
- Federated MoE expert routing across nodes
- Cross-community federation
- End-to-end encryption of chat between users
- Capability tokens (auth is per-request signing only)
- OCR, translation, speech, image generation services (designed; not coded)
- Mobile native app (web only)
- OTLP trace export
- The signed nightly snapshot mechanism (events keep accumulating in MVP)

---

## 22. Phase 2 — post-hackathon (1–3 months)

### 22.1 Internet relay & cross-LAN federation

A small Rust or Python relay any participant can host. Helps NAT'd peers reach each other. Used to bootstrap federation between, e.g., Issum and Geldern communities.

### 22.2 Federated learning experiments

Each anchor periodically computes LoRA gradients on local conversations (consent-required), sends only the gradient deltas to other anchors, averages, applies. A simple version of FedAvg, scoped to LoRA layers of the local LLM. Not full federated learning — practical and scoped.

### 22.3 Capability tokens

OAuth-style short-lived tokens for fine-grained delegation. Especially useful for Bridge nodes between communities.

### 22.4 OCR + translation services

For ingesting paper documents (lamppost notices) and serving the Plattdeutsch / Niederrhein angle.

### 22.5 Speech I/O

STT (Whisper) and TTS (Christof's existing XTTS-v2 + Edge-TTS pipeline). Particularly valuable for elderly community members in an emergency context.

### 22.6 Hetzner / IONOS deployment

A relay tier hosted by Christof at `relay.hearthnet.de`, with the existing PHP 8.3 + Python bridge infrastructure used for ki-fusion-labs. Free for small communities, paid for larger ones (revenue path 1).

### 22.7 Mobile native client

Flutter or React Native. Bypasses the "must keep browser tab open" limitation. Push notifications via the existing relay tier.

### 22.8 Marketplace search via embeddings

`market.search@1.0` registered as a capability. Embed posts on creation, semantic search. Probably <1 day given the infrastructure is there.

### 22.9 Federated identity import

Optional: import an existing identity (HF, GitHub key, etc.) to bootstrap trust. Decouples HearthNet identity from device.

### 22.10 Improved topology visualisation

3D mesh, request heatmaps, historical replay. Pure polish, but valuable for demos and selling.

---

## 23. Phase 3 — research-shaped (6–12 months)

### 23.1 Distributed-layer inference experiment

A genuinely-distributed inference path for one specific small model (1.5B–3B), Petals-style, as a feature flag. Acceptable latency probably only on Ethernet-connected nodes within the same household. The point is the demo, not production. Wire it under the existing `llm.chat` capability with a `distributed: true` parameter and a clear latency warning.

### 23.2 MoE-style expert routing

Each community has expert nodes: "the electrician's node has the Schaltplan corpus", "the gardener's node has the Pflanzen knowledge". The router learns which questions to send where. Mix human + AI experts: route a question to a real neighbour as fallback. Connect to the marketplace.

### 23.3 LoRa "I exist" beacons

868MHz transmitter on an anchor. Phones with LoRa modules learn community exists in range. Useful in real disaster scenarios where WiFi is gone.

### 23.4 Christof's research integrations

- **Proto-Cognitive Architecture v5.2** as an `llm.chat` backend with experimental episodic-memory features
- **Hebbian residual memory** experiments on Qwen2.5-1.5B as another backend
- **BitNet 1.58-bit** quantised models for very low resource nodes (Pi 5 + USB SSD)
- **EBKH** as the evidence layer for marketplace truth-checking (claim-graph for "is this actually safe drinking water?")

### 23.5 Civil-defence pilot

Pilot with one NRW municipality. Bevölkerungsschutz partners. Real test under a planned blackout exercise. This is the credibility-building step toward larger deployments.

---

## 24. Phase 4 — long-term vision

A "neighbourhood internet" where:

- Communities own their compute
- Communities federate with adjacent communities
- Communities can survive multi-day outages
- AI is a community resource like a library or a kitchen, not a subscription
- The protocol is open, the implementation is reference, the ecosystem is many

The grand version of HearthNet looks more like a protocol (think Matrix or ActivityPub) than a product. We are building the reference implementation that proves the protocol is worth standardising.

---

## 25. Reuse from existing systems

Christof has built a lot of this stuff already. The PRD is *not* "build everything from scratch". It is "compose the existing FORGE/EBKH/NEXUS/PicoClaw work behind a coherent mesh protocol". Concretely:

| Existing system | What it gives HearthNet |
|---|---|
| **FORGE** (15 HF Spaces, multi-agent platform) | Service skeleton, tool plumbing, GDPR delete endpoints, auto-seeding patterns |
| **EBKH** (event-sourced claim graph, 28 packages, 48 event types) | The event log, snapshot pattern, schema-versioned events |
| **NEXUS** (LLM gateway) | Multi-provider LLM adapter with health/latency tracking |
| **htmlClaw / OpenClaw** (single-file WebGPU browser agent) | Possible browser-only node profile (Phase 2): a HearthNet node that lives entirely in a tab |
| **Proto-Cognitive Architecture v5.2** | Optional advanced LLM backend with episodic memory |
| **BitNet kernel** | Backend for ultra-low-resource nodes |
| **DSGVO Löschprotokoll** (MinIO + PostgreSQL + FastAPI + Streamlit) | Audit-trail and erase patterns for compliance |
| **Florence-2 + FLUX.1 pipeline** | Image services backend |
| **smolagents + Edge-TTS / XTTS-v2 podcast generator** | Speech services backend |
| **LM Studio at 192.168.188.25:1234** | The first real LLM backend during dev |
| **JARVIS / TheCore notes** | Agent architecture inspiration for the router |
| **HuggingFace MCP work (Chris4K)** | MCP integration in Phase 2 (HearthNet nodes as MCP servers) |

The build effort is real, but it is integration effort, not invention effort. That ratio is what makes this hackathon-doable.

---

## 26. Technology stack

### 26.1 Languages

- **Python +3.11+** — primary, for everything except where noted
- **Rust** — Phase 2 relay (optional, Python relay fine for MVP)
- **HTML/CSS/JavaScript** — UI, front, mobile client, no frameworks (Christof preference)
- **C++** — only via llama.cpp, not authored

### 26.2 Libraries

| Concern | Library | Why |
|---|---|---|
| Web server | FastAPI + uvicorn | Christof's existing stack |
| UI | Gradio 6.0.0 | Hackathon requirement, Christof familiar |
| Discovery | python-zeroconf | de-facto for mDNS |
| Crypto | PyNaCl (Ed25519) + cryptography (TLS) | Boring, secure |
| Hashing | blake3 | Fast CID hashing |
| Vector DB | ChromaDB (file-based) | Local-first, simple |
| Embeddings | sentence-transformers | BGE-small is plenty |
| LLM | llama-cpp-python OR ollama HTTP | Backend-agnostic via adapter |
| Event store | SQLite + JSON | Zero-config, transactional |
| Pub-sub | In-process asyncio + HTTP push for remote | No broker needed |
| Topology viz | Cytoscape.js embedded in Gradio HTML | Christof has used Cytoscape before |
| Charts | Chart.js | Christof has used Chart.js before |
| CLI | Click | Standard |
| Testing | pytest + pytest-asyncio | Standard |
| Tracing | OpenTelemetry SDK (Phase 2) | Optional |

### 26.3 Explicit non-choices

- **Not** Node.js or npm — Christof preference
- **Not** React or any heavy frontend framework — Christof preference, also Gradio doesn't need it
- **Not** Docker as a hard requirement — single-binary install must work
- **Not** a custom binary protocol — JSON over HTTP is enough and debuggable

---

## 27. Deployment topologies

### 27.1 Home (3 nodes typical)

- Anchor on a workstation
- 1–2 Hearth nodes on laptops
- 0–3 Spark thin clients on phones / Pi

### 27.2 Small business

- 1–2 Anchors in the back office
- 5–15 Spark clients at workstations
- Optional Bridge to a sister branch via Phase 2 relay

### 27.3 Civic / municipal

- Anchor per community building (Feuerwache, Bürgerhaus, Kirche)
- Federation between buildings
- Sparks via citizen smartphones with the mobile client
- Bridge to civil defence systems (Phase 3, requires policy work)

### 27.4 Disaster pilot

- Mobile anchor (camper-van rig with battery + Starlink fallback)
- LoRa beacons for spread
- Manual Spark distribution (USB drives with the mobile client)

---

## 28. Go-to-market & monetisation

These are aspirational, not part of the hackathon. Including them because the PRD is also a thinking document.

### 28.1 Path A — retail-continuity pilot

stores depend on technical devices. Internet drops happen. A small HearthNet anchor in the back room of every store plus Sparks at every cashier desk = an internal mesh for orders, inventory checks, and customer comms that survives a WAN outage. Internal pilot first; later an outward-facing product offered to other cold-chain retailers.

Estimated revenue path: 1–2 year horizon, internal first.

### 28.2 Path B — NRW Bevölkerungsschutz pilot

Each Kreis has civil-defence mandates. A neighbourhood AI mesh that works without internet fits exactly. Grant-fundable. Stakeholders: Kreis Kleve Bevölkerungsschutz, THW, optionally DRK. Christof's local Sankt-Martins-Comité contacts are a wedge.

Estimated revenue path: 6–12 months, public-sector procurement realities apply.

### 28.3 Path C — HearthNet-in-a-Box appliance

Mini-PC (e.g. Beelink + small NVIDIA GPU or Intel Arc) pre-installed with the stack, a 1TB SSD, a curated emergency corpus, a default model. Ships with a printed booklet for the non-technical setup. Customers: community groups, churches, Vereine, prepper-adjacent, off-grid-curious.

Margins thin on hardware, real margin on optional yearly support + corpus updates.

Estimated revenue path: 3–6 months to first prototype, viable hobby-business scale.

### 28.4 Path D — hosted relay tier

`relay.hearthnet.de` on Hetzner. Free for tiny communities (≤5 anchors), paid above. Bring-your-own-domain for organisations. Used for cross-LAN bootstrap, mobile push, and store-and-forward when no anchor is online for a recipient.

Estimated revenue path: 3 months to launch, low-margin but recurring.

### 28.5 Path E — open-source consulting

The AGPL kernel + paid integration for organisations that want HearthNet inside their infrastructure. Standard open-core business model. Probably the highest near-term revenue per hour.

### 28.6 Anti-paths

- No "neighbourhood crypto-token". Tempting and wrong.
- No ad-supported model. Defeats the purpose.
- No closed-source kernel. Defeats the trust model.

---

## 29. Risks & mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| mDNS blocked on demo venue WiFi | Medium | High | Travel router on stage, UDP broadcast as fallback, fake-mesh dry-run mode |
| GPU node OOM mid-demo | Low | High | Pre-warmed model, conservative `max_concurrent`, smaller model as fallback |
| Demo computer dies | Low | Catastrophic | Two laptops, identical config, hot-swappable |
| Distributed inference (Phase 3) attempted in MVP | Medium | High | Crossed-out in scope, behind feature flag if anyone tries |
| Capability schema churn | Medium | Medium | Lock v1 schemas before M4 starts, treat as ABI |
| Christof's bandwidth (newborn, Elternzeit) | High | High | Demo-driven scope; M7 and M10 are cuttable |
| Privacy backlash ("you're routing my data through neighbours?") | Medium | Medium | Clear local-first defaults, signed-and-encrypted-in-transit, explicit "personal" corpus that never leaves device |
| GDPR review | Medium | Medium | Reuse DSGVO Löschprotokoll patterns; explicit erase path |
| Hardware vendor lock-in (NVIDIA-only) | Medium | Low | llama.cpp + ollama supports Apple Silicon and AMD; Ollama is the default for non-NVIDIA |
| "It's just a worse cloud" criticism | High | Medium | Lead with the resilience demo, not the AI quality argument |

---

## 30. Success metrics

### 30.1 Hackathon success

- Demo runs end-to-end without intervention on first try in the judge session
- Topology visualisation is clear enough that a non-technical observer can describe what is happening
- At least one judge asks "can I run this at home?"
- Submission is delivered before deadline
- Code is published, repo is clean, README has a one-command quickstart

### 30.2 Post-hackathon technical success (3 months)

- Three real households running HearthNet for at least a week each
- Median end-to-end latency under 2s for `llm.chat` in a typical home LAN
- Zero data-loss incidents in event log under partition + rejoin scenarios
- Mobile client usable on iOS Safari and Android Chrome
- 80%+ test coverage on the bus

### 30.3 Product success (12 months)

- At least one of the four monetisation paths has produced revenue
- One outside contributor merged code
- One academic citation or thoughtful blog post about the architecture
- 100+ HF Spaces stars (proxy for community interest)

---

## 31. Open questions

These need resolution but do not block the hackathon.

1. **Single binary or pip install?** Hackathon: pip. Long-term: single binary built with PyInstaller or Nuitka.
2. **Storage location standard?** XDG on Linux/macOS, `%APPDATA%` on Windows. Decision: follow `platformdirs` library.
3. **Time sync?** Lamport clocks make us mostly clock-independent, but UI timestamps suffer if clocks drift. Decision: display "X minutes ago" only; show absolute time only on the local device's wall clock.
4. **Mobile client served from any anchor — what about the URL?** mDNS for `hearthnet.local` is the goal. Browser support varies. Decision: print the IP+port in the QR code as a fallback.
5. **How does a Spark survive its anchor going down?** With a list of known peers. Decision: each Spark caches the last 10 peer manifests; tries them in order if the bound anchor disappears.
6. **What's the bus's behaviour when two local services register the same capability?** Both registered; router prefers based on declared params. No conflict.
7. **Can a non-member observe public traffic?** Yes — they see signed manifests by virtue of mDNS. They cannot make calls. Decision: keep this; visibility is the price of zero-config.
8. **Federation between communities with conflicting member sets?** Out of scope for MVP.
9. **Web of trust visualisation?** Phase 2 polish.
10. **Should anchors be able to refuse a capability call?** Yes — `unauthorized` is a valid response. Refusal is fine.

---

## 32. Glossary

| Term | Meaning |
|---|---|
| **Anchor** | Always-on node with GPU + storage, primary provider |
| **Bus (capability bus)** | The L3 routing component every service registers with |
| **Capability** | A named, versioned, schema-bound RPC offered by a node |
| **CID** | Content identifier (BLAKE3 hash) used for content-addressed storage |
| **Community** | A trust root; a group of nodes sharing a root key and event log |
| **Emergency mode** | UI + behavioural state when internet detection reports offline |
| **Federation** | Cross-community trust and capability access |
| **Hearth** | Mid-tier node, typically a laptop |
| **Lamport clock** | Logical counter used for event ordering |
| **Manifest** | A signed JSON document (node manifest or community manifest) |
| **Node** | One running HearthNet process |
| **Profile** | One of `anchor`, `hearth`, `spark`, `bridge` — determines services |
| **Service** | An L4 module providing one or more capabilities |
| **Spark** | Thin client (Pi, mobile, browser) |
| **Stable / experimental** | Capability stability flags |

---

## 33. Appendix A — capability namespace allocation

| Prefix | Owner service | Examples |
|---|---|---|
| `llm.*` | LLM service | `llm.chat`, `llm.complete`, `llm.classify` |
| `embed.*` | Embedding service | `embed.text`, `embed.image` |
| `rag.*` | RAG service | `rag.query`, `rag.ingest`, `rag.list_corpora` |
| `file.*` | File service | `file.read`, `file.list`, `file.advertise` |
| `market.*` | Marketplace | `market.list`, `market.post`, `market.search` |
| `chat.*` | Chat | `chat.send`, `chat.history` |
| `community.*` | Trust ops | `community.invite`, `community.revoke` |
| `federation.*` | Cross-community | `federation.peer.add`, `federation.relay` |
| `ocr.*` | OCR (Phase 2) | `ocr.image`, `ocr.pdf` |
| `tts.*` `stt.*` | Speech (Phase 2) | `tts.synthesize`, `stt.transcribe` |
| `trans.*` | Translation (Phase 2) | `trans.text` |
| `img.*` | Images (Phase 2) | `img.describe`, `img.generate` |
| `experimental.*` | Anything not promoted | `experimental.distributed_llm.chat` |

Reserved prefixes; no service may take a name outside its declared prefix.

---

## 34. Appendix B — example end-to-end trace

A user on the laptop asks *"Wie reinige ich Regenwasser ohne Strom?"*. The trace, as it would appear in the trace log:

```
t+0ms     UI: user submits query, calls local bus capability "llm.chat@1.0"
t+1ms     Bus: routing query, looking for "llm.chat" providers
t+2ms     Bus: candidates: [anchor: 7H4G-..., self: 9JKM-...]
          anchor: p50=820ms, in_flight=0/4, success=0.99
          self:   would-be: needs to load model, ~3000ms cold
t+3ms     Bus: scoring → anchor wins (lower latency)
t+4ms     Bus: opening stream to anchor
t+7ms     Anchor: receives request, validates signature, schema OK
t+8ms     Anchor LLM: starts generation
t+9ms     Anchor: calls local "rag.query@1.0" with the user message
t+11ms    Anchor RAG: embeds query (local embed.text)
t+24ms    Anchor RAG: vector search returns 4 chunks from emergency PDF
t+25ms    Anchor LLM: receives chunks, builds context, continues
t+182ms   Anchor: streams first token to laptop
t+184ms   Laptop UI: animates edge from anchor → self, shows first token
t+1402ms  Anchor: emits "done" event, stream closes
t+1404ms  Laptop UI: animation completes, shows source citation
t+1405ms  Bus: records trace: 1401ms, 178 tokens, success
```

Total perceived latency: under 1.5 seconds, with token streaming from ~200ms. Visible routing on screen.

---

## 35. Appendix C — example minimal node startup code

This is illustrative, not normative. Real implementation is split across modules.

```python
# hearthnet/node.py
import asyncio
from hearthnet.identity import load_or_generate_keys, load_community
from hearthnet.discovery import mdns_loop, udp_broadcast_loop
from hearthnet.bus import CapabilityBus
from hearthnet.transport import HttpServer
from hearthnet.services.llm import LlmService
from hearthnet.services.rag import RagService
from hearthnet.services.market import MarketplaceService
from hearthnet.ui.gradio_app import build_ui

async def main():
    keys = load_or_generate_keys()
    community = load_community()
    bus = CapabilityBus(node_id=keys.node_id, community=community)

    # Register local services
    bus.register_service(LlmService(backend="llama_cpp", model="qwen2.5-7b@q4"))
    bus.register_service(RagService(corpus="niederrhein-emergency"))
    bus.register_service(MarketplaceService(community=community))

    # Start transport + discovery
    server = HttpServer(bus=bus, port=7080, keys=keys)
    await asyncio.gather(
        server.run(),
        mdns_loop(bus),
        udp_broadcast_loop(bus),
        emergency_detector(bus),
        build_ui(bus).launch_async(port=7860),
    )

if __name__ == "__main__":
    asyncio.run(main())
```

That is the whole shape. Everything else is filling in.

---

*End of HearthNet PRD v2. Split into per-section docs once implementation starts.*