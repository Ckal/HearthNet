# HearthNet Phase 3 — Spec Set Overview

**Phase 3 scope:** research-shaped, 6–12 months. This is where HearthNet stops being a product and starts being a protocol. Each module here is an investment in a long-term capability where the engineering is the easy part — the hard part is establishing trust, governance, and standards.

**Stance:** Phase 3 specs are **roadmaps**, not contracts. Where a Phase-1/2 spec answers "what does this *do*?", a Phase-3 spec answers "what would we *build* if we were ready to commit?". Concrete enough to start, loose enough to be wrong about details without invalidating the direction.

---

## 0. Reading these specs

Phase 3 specs deviate from the Phase 1 / 2 template in three respects:

1. **Stability tag is `experimental` for new capabilities** unless explicitly promoted later. Mesh nodes ignore experimental capabilities unless the operator opts in via `policy.research.enable = true`.
2. **Each module carries an "Open research questions" section** that is longer than the spec itself, by design. Phase 3 modules answer *some* of their open questions before shipping; the rest stay open.
3. **Acceptance criteria are described, not enumerated**. The point isn't to grade an implementation against a checklist; it's to say "we'll know this is working when…"

If you read a Phase 3 spec and feel uncertain about how something works, that uncertainty is faithful to the state of the work. The spec is doing its job by being honest about that.

---

## 1. Module map (Phase 3)

### New numbered modules

| ID  | Module                       | Spec file                                       | Concern                                                              |
|-----|------------------------------|-------------------------------------------------|----------------------------------------------------------------------|
| M26 | Distributed Inference        | `modules/M26-distributed-inference.md`          | Layer-sharded LLMs across nodes (Petals-style), small models only    |
| M27 | MoE Expert Routing           | `modules/M27-moe-routing.md`                    | Route queries to the right expert (machine or human) via learned scorer |
| M28 | Federated Learning           | `modules/M28-fedlearn.md`                       | FedAvg on LoRA layers; per-community fine-tuning without sharing data |
| M29 | LoRA Long-Distance Beacons   | `modules/M29-lora-beacons.md`                   | 868MHz "community alive" beacons; no AI traffic; emergency-only       |
| M30 | Evidence / EBKH              | `modules/M30-evidence-ebkh.md`                  | Claim graph alongside the event log; provenance + verifiability       |
| M31 | Civil Defence Pilot          | `modules/M31-civil-defense.md`                  | THW / DRK / KatS bridge; compliance profile; audit trail              |
| M32 | Protocol Standardisation     | `modules/M32-protocol-standard.md`              | Reference implementation, conformance suite, governance for the spec |

### New cross-cutting modules

| ID  | Module                | Spec file                                         | Concern                                              |
|-----|-----------------------|---------------------------------------------------|------------------------------------------------------|
| X08 | Tensor Transport      | `cross-cutting/X08-tensor-transport.md`           | High-throughput chunked tensor passing for M26       |
| X09 | Conformance Suite     | `cross-cutting/X09-conformance-suite.md`          | Black-box tests defining what "HearthNet-compliant" means |

### Modifications to earlier modules

| Phase 1/2 module | Phase 3 extension |
|------------------|-------------------|
| M03 Bus          | Optional MoE routing layer between dispatcher and handler (M27) |
| M04 LLM          | Optional `experimental.distributed_llm.chat@1.0` backend (M26) |
| X02 Event log    | Optional `evidence.*` claim records side-by-side with events (M30) |
| M14 Federation   | Federated learning rounds use federation as the trust substrate (M28) |
| X03 Observability | Per-call expert-routing trace; per-shard tensor-transport metrics (M27, X08) |

---

## 2. Dependency graph (Phase 3 additions on top of Phases 1–2)

```
                ┌─────────────────────────────────────────────┐
                │       Phase 1 + Phase 2 (unchanged)         │
                └────┬────────────────┬──────────────┬────────┘
                     │                │              │
                     ▼                ▼              ▼
              ┌──────────┐      ┌──────────┐    ┌──────────┐
              │  X08     │      │  M27     │    │  M30     │
              │  Tensor  │      │  MoE     │    │  EBKH    │
              │  Transp. │      │  Routing │    │  Evidence│
              └─────┬────┘      └─────┬────┘    └────┬─────┘
                    ▼                 │              │
              ┌──────────┐            │              │
              │  M26     │            │              │
              │  Distrib.│            │              │
              │  Infer.  │            │              │
              └──────────┘            │              │
                                      ▼              ▼
                                ┌──────────┐   ┌──────────┐
                                │  M28     │   │  M31     │
                                │  FedLearn│   │  CivDef. │
                                └──────────┘   └──────────┘

       Standalone (no software deps, governance / hardware):
                                ┌──────────┐
                                │  M29     │   (hardware)
                                │  LoRa    │
                                │  Beacons │
                                └──────────┘
                                ┌──────────┐
                                │  X09     │   (process)
                                │  Conform.│
                                └──────────┘
                                ┌──────────┐
                                │  M32     │   (governance)
                                │  Standard│
                                └──────────┘
```

Most Phase 3 modules are independent of each other. The exceptions:
- M26 depends on X08
- M27 informs M26 (MoE routing picks which expert/shard)
- M28 reuses M14 federation for cross-community rounds
- M31 reuses M30 for evidence-grade emergency claims

---

## 3. File tree additions

```
hearthnet/
├── distributed_inference/       # M26
│   ├── __init__.py
│   ├── shard.py
│   ├── pipeline.py
│   ├── routing.py
│   └── backends/
│       ├── petals_like.py
│       └── small_model_layered.py
│
├── moe/                         # M27
│   ├── __init__.py
│   ├── router.py
│   ├── scorer.py
│   └── human_in_the_loop.py
│
├── fedlearn/                    # M28
│   ├── __init__.py
│   ├── coordinator.py
│   ├── round.py
│   ├── lora_diff.py
│   └── aggregation.py
│
├── lora_beacons/                # M29 — hardware integration; tiny Python surface
│   ├── __init__.py
│   ├── beacon_bridge.py         # serial protocol to a LoRa USB stick
│   └── policy.py
│
├── evidence/                    # M30
│   ├── __init__.py
│   ├── claim.py
│   ├── claim_graph.py
│   ├── provenance.py
│   └── ebkh_bridge.py           # bridge to Christof's EBKH v3+
│
├── civil_defense/               # M31
│   ├── __init__.py
│   ├── profile.py               # THW / DRK / KatS member types
│   ├── audit.py
│   └── nrw_katastrophenschutz.py
│
├── transport/
│   └── tensor.py                # X08
│
└── conformance/                 # X09
    ├── __init__.py
    ├── runner.py
    ├── suites/
    │   ├── identity.py
    │   ├── transport.py
    │   ├── bus.py
    │   ├── services.py
    │   └── federation.py
    └── report.py

protocol/                        # M32 — separate top-level dir at repo root
├── README.md
├── spec/                        # the protocol spec, decoupled from the impl
│   ├── 00-overview.md           # mirror of CAPABILITY_CONTRACT but
│   ├── 01-identity.md           # implementation-agnostic
│   └── ...
└── governance/
    ├── CHANGELOG.md
    ├── CONTRIBUTING.md
    └── ROADMAP.md
```

---

## 4. Conventions delta from Phase 2

### 4.1 New `experimental` namespace

A Phase-3 capability MAY be advertised as `experimental.<name>@<ver>`. Mesh nodes default to **not registering** experimental capabilities; the operator must opt in via:

```toml
[policy.research]
enable                = true
enabled_capabilities  = ["experimental.distributed_llm.chat@1.0", "experimental.fedlearn.round.*"]
```

Once a capability is sufficiently proven, it is promoted out of the `experimental.` prefix in a contract bump.

### 4.2 New type aliases

```python
# additions to hearthnet/types.py

ShardID         = str        # "<model_id>:<layer_range>"
ExpertID        = str        # opaque, refers to a routable subsystem
ClaimID         = str        # ULID
RoundID         = str        # fedlearn round identifier (ULID)
LoraBeaconID    = str        # 8-byte hex, hardware-issued
EvidenceLevel   = Literal["unverified","cited","cross_referenced","attested","disputed"]
ExpertKind      = Literal["model","human","service","external"]
```

### 4.3 New constants

```python
# additions to hearthnet/constants.py — Phase 3

# Distributed inference (M26)
DISTRIBUTED_MAX_SHARDS_PER_REQUEST  = 16
DISTRIBUTED_SHARD_HEALTH_TIMEOUT_S  = 30
DISTRIBUTED_FALLBACK_TO_LOCAL_AFTER_FAILURES = 2

# MoE routing (M27)
MOE_ROUTER_TOP_K                    = 3
MOE_ROUTER_TRAIN_MIN_EXAMPLES       = 200
MOE_ROUTER_RETRAIN_EVERY_HOURS      = 24

# Federated learning (M28)
FEDLEARN_MAX_ROUND_MINUTES          = 120
FEDLEARN_MIN_PARTICIPANTS           = 3
FEDLEARN_MAX_LORA_RANK              = 64
FEDLEARN_GRAD_CLIP                  = 1.0
FEDLEARN_DP_NOISE_SCALE_DEFAULT     = 0.0    # off by default; off-by-default differential privacy

# Evidence (M30)
EVIDENCE_CLAIM_TTL_DAYS_DEFAULT     = 365
EVIDENCE_MAX_PROVENANCE_DEPTH       = 16

# Civil defence (M31)
CIVDEF_AUDIT_RETENTION_YEARS        = 10
CIVDEF_HEARTBEAT_SECONDS            = 60

# Tensor transport (X08)
TENSOR_CHUNK_BYTES                  = 1_048_576   # 1 MB
TENSOR_FLOW_CONTROL_WINDOW          = 16          # chunks
TENSOR_COMPRESSION_THRESHOLD_BYTES  = 65_536

# LoRa beacons (M29)
LORA_BEACON_PERIOD_SECONDS_DEFAULT  = 600          # 10 minutes
LORA_BEACON_MAX_PAYLOAD_BYTES       = 32
```

---

## 5. Build order (Phase 3)

Phase 3 is not a release; it is a set of long-running tracks. Suggested ordering by independence + value:

| Track | Modules                          | Outcome                                                                       |
|-------|----------------------------------|-------------------------------------------------------------------------------|
| A     | X09 Conformance + M32 Standard   | Other people can build HearthNet-compliant nodes                              |
| B     | M30 Evidence / EBKH              | Marketplace claims and emergency posts carry provenance                        |
| C     | M27 MoE Routing (machines only)  | Better answers for free; routes RAG queries to best-suited backend             |
| D     | M27 + M28 (human routing)        | Neighbour gets pinged when their expertise matches                            |
| E     | M28 FedLearn                     | Communities co-train a small LoRA without sharing source data                  |
| F     | X08 + M26 Distributed Inference  | Two anchors jointly serve a 7B model; large models become feasible LAN-wide   |
| G     | M29 LoRa Beacons                 | Resilient "I am alive" pings during regional internet outages                  |
| H     | M31 Civil Defence Pilot          | A real Niederrhein THW Ortsverband uses HearthNet for an exercise              |

Tracks can run in parallel. None of them block the existing Phase-2 system.

---

## 6. Spec versioning

- Capability Contract bumps to **v3.0** but the bump is *additive*. v2 nodes coexist with v3 nodes; experimental capabilities simply aren't seen by v2 nodes.
- The first concrete deliverable of Track A (M32) is to **decouple** the protocol spec from the implementation. After that, the contract has its own version track separate from the Python implementation's version.

---

## 7. Out-of-band documents (Phase 3)

- **RESEARCH_AGENDA.md** — the deeper "why" for each module; intended audience: PhD students and grant reviewers
- **GOVERNANCE.md** — how spec changes are proposed, reviewed, and accepted; ties into M32
- **ETHICS_REVIEW.md** — the framework for evaluating MoE-driven routing-to-humans (M27) and fedlearn-on-personal-data (M28)
- **CIVDEF_AGREEMENT_TEMPLATE.md** — the MoU template for a civil-defence pilot

---

## 8. What is NOT in Phase 3

Even with all of Phase 3 done, the following remain explicit non-goals:

- A central directory of communities. There is no "HearthNet.com" listing all communities. Discovery is via word of mouth + DHT + federation. Pushed indefinitely.
- An app store for capabilities. Capabilities are code in the source tree, reviewed by maintainers. Not pluggable at runtime by untrusted code.
- A consensus protocol (Paxos, Raft). Communities do not vote on shared state beyond event-log gossip. Federation does not imply consensus.
- A cryptocurrency / token economy. Not even for fedlearn incentives. Reputational signals only.
- AGI. Even the distributed inference module targets at-most-mid-sized models (7B-class). The thesis is "small models close to people are more useful than large models far away", and Phase 3 doesn't change that.
