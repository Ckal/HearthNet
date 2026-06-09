# HearthNet Phase 3 — Implementation Reference

**Spec set:** v3.0 — *experimental*
**Status:** Research-shaped. Names and contracts may shift before promotion to stable.

This document is the symbol index and quick-reference for everything introduced in Phase 3. It mirrors the structure of Phase 1's and Phase 2's `IMPLEMENTATION_REFERENCE.md`, so a maintainer can find the relevant spec section, file, class, capability, event, or constant by name.

Read this with the Phase 1 + Phase 2 references already in hand. Phase 3 is purely additive; it does not redefine anything from earlier phases.

---

## 1. Module index

| ID | Name | Status | Spec file |
|----|------|--------|-----------|
| M26 | Distributed Inference (layer sharding) | experimental | [phase-3/modules/M26-distributed-inference.md](modules/M26-distributed-inference.md) |
| M27 | MoE Expert Routing | experimental | [phase-3/modules/M27-moe-routing.md](modules/M27-moe-routing.md) |
| M28 | Federated Learning (LoRA aggregation) | experimental | [phase-3/modules/M28-fedlearn.md](modules/M28-fedlearn.md) |
| M29 | LoRa Hardware Beacons | experimental | [phase-3/modules/M29-lora-beacons.md](modules/M29-lora-beacons.md) |
| M30 | Evidence Graph & EBKH Integration | experimental | [phase-3/modules/M30-evidence-ebkh.md](modules/M30-evidence-ebkh.md) |
| M31 | Civil Defense (NRW Bevölkerungsschutz) | experimental | [phase-3/modules/M31-civil-defense.md](modules/M31-civil-defense.md) |
| M32 | Protocol Standardisation & Conformance | provisional | [phase-3/modules/M32-protocol-standard.md](modules/M32-protocol-standard.md) |
| X08 | Tensor Transport | experimental | [phase-3/cross-cutting/X08-tensor-transport.md](cross-cutting/X08-tensor-transport.md) |
| X09 | Conformance Suite | provisional | [phase-3/cross-cutting/X09-conformance-suite.md](cross-cutting/X09-conformance-suite.md) |

All `experimental` modules are gated by per-module feature flags in `hearthnet/config.py` and default to `False`.

---

## 2. Capability index

All Phase 3 capabilities (except `protocol.*`) live in the `experimental.*` namespace. The bus refuses to register them unless the corresponding feature flag is on.

### 2.1 Distributed Inference (M26)

| Capability | Module | Notes |
|------------|--------|-------|
| `experimental.distributed_llm.shard.list` | M26 | Local advertisement of shards we host |
| `experimental.distributed_llm.shard.connect` | M26 | Negotiate an X08 tensor session |
| `experimental.distributed_llm.shard.forward` | M26 | Run forward through a hosted shard |
| `experimental.distributed_llm.pipeline.plan` | M26 | Construct a layer pipeline for a model |
| `experimental.distributed_llm.pipeline.run` | M26 | Execute a planned pipeline |
| `experimental.distributed_llm.pipeline.status` | M26 | Pipeline state and stats |

### 2.2 MoE Routing (M27)

| Capability | Module | Notes |
|------------|--------|-------|
| `experimental.moe.expert.register` | M27 | Register self as an expert for some topics |
| `experimental.moe.expert.list` | M27 | List registered experts |
| `experimental.moe.expert.unregister` | M27 | Withdraw expert registration |
| `experimental.moe.route.query` | M27 | Get top-K experts for a query |
| `experimental.moe.route.handoff` | M27 | Initiate human-in-the-loop handoff |
| `experimental.moe.feedback.record` | M27 | Record outcome for scorer training |

### 2.3 Federated Learning (M28)

| Capability | Module | Notes |
|------------|--------|-------|
| `experimental.fedlearn.round.announce` | M28 | Coordinator announces a round |
| `experimental.fedlearn.round.list` | M28 | List open rounds |
| `experimental.fedlearn.round.join` | M28 | Participant joins a round |
| `experimental.fedlearn.round.submit` | M28 | Submit gradient delta |
| `experimental.fedlearn.round.status` | M28 | Get round state |
| `experimental.fedlearn.round.finalize` | M28 | Coordinator finalises and aggregates |
| `experimental.fedlearn.adapter.fetch` | M28 | Fetch an aggregated adapter by SHA |
| `experimental.fedlearn.adapter.apply` | M28 | Apply adapter to session or node |

### 2.4 LoRa Beacons (M29)

| Capability | Module | Notes |
|------------|--------|-------|
| `experimental.lora.status` | M29 | Hardware and link status |
| `experimental.lora.beacon.send` | M29 | Send a normal beacon |
| `experimental.lora.panic.send` | M29 | Send a panic burst |
| `experimental.lora.peer.list` | M29 | Known LoRa peers |
| `experimental.lora.peer.verify` | M29 | TOFU-confirm a peer's NodeID binding |
| `experimental.lora.recent_beacons` | M29 | Recent RX'd beacons |
| `experimental.lora.duty_cycle` | M29 | Current duty-cycle budget status |

### 2.5 Evidence Graph (M30)

| Capability | Module | Notes |
|------------|--------|-------|
| `experimental.evidence.claim.assert` | M30 | Assert a new claim |
| `experimental.evidence.claim.dispute` | M30 | Dispute an existing claim |
| `experimental.evidence.claim.attest` | M30 | Attest to an existing claim |
| `experimental.evidence.claim.get` | M30 | Fetch a single claim by ID |
| `experimental.evidence.claim.query` | M30 | Query claims by triple |
| `experimental.evidence.provenance.trace` | M30 | Walk the derivation graph |
| `experimental.evidence.subject.summary` | M30 | Multi-claim summary for a subject |
| `experimental.evidence.ebkh.sync` | M30 | Sync with external EBKH endpoint |

### 2.6 Civil Defense (M31)

| Capability | Module | Notes |
|------------|--------|-------|
| `experimental.civdef.alert.publish` | M31 | Role-cert-gated alert publication |
| `experimental.civdef.alert.cancel` | M31 | Cancel an active alert |
| `experimental.civdef.alert.list` | M31 | List active alerts (filtered) |
| `experimental.civdef.alert.get` | M31 | Fetch an alert envelope |
| `experimental.civdef.alert.subscribe` | M31 | Subscribe to alerts matching a filter |
| `experimental.civdef.alert.ack` | M31 | Acknowledge an alert |
| `experimental.civdef.alert.acks` | M31 | List acks for an alert |
| `experimental.civdef.role.register` | M31 | Register a role certificate |
| `experimental.civdef.role.list` | M31 | List registered certificates |
| `experimental.civdef.role.revoke` | M31 | Revoke a certificate |
| `experimental.civdef.audit.export` | M31 | Export tamper-evident audit chain |

### 2.7 Protocol (M32) — stable

| Capability | Module | Notes |
|------------|--------|-------|
| `protocol.version.list` | M32 | Versions supported |
| `protocol.self.describe` | M32 | Implementation descriptor |
| `protocol.conformance.report` | M32 | Run / fetch conformance report |
| `protocol.registry.list` | M32 | Known implementations |
| `protocol.registry.announce` | M32 | Announce self to registry |

---

## 3. Event types

All Phase 3 event types follow the convention `<area>.<entity>.<verb>` and are recorded in the X02 event log.

### 3.1 Distributed inference

```
distributed_llm.shard.advertised
distributed_llm.shard.withdrawn
distributed_llm.pipeline.planned
distributed_llm.pipeline.started
distributed_llm.pipeline.shard_failed
distributed_llm.pipeline.failover
distributed_llm.pipeline.completed
distributed_llm.pipeline.cancelled
```

### 3.2 MoE

```
moe.expert.registered
moe.expert.unregistered
moe.route.computed
moe.handoff.initiated
moe.handoff.accepted
moe.handoff.declined
moe.handoff.timed_out
moe.feedback.recorded
```

### 3.3 Federated learning

```
fedlearn.round.announced
fedlearn.round.joined
fedlearn.round.consent.granted
fedlearn.round.submitted
fedlearn.round.aggregated
fedlearn.round.completed
fedlearn.round.aborted
fedlearn.round.takeover
fedlearn.adapter.published
fedlearn.adapter.applied
```

### 3.4 LoRa

```
lora.beacon.sent
lora.beacon.received
lora.panic.sent
lora.panic.received
lora.peer.unknown
lora.peer.verified
lora.peer.conflict
lora.duty_cycle.exhausted
lora.duty_cycle.overridden
lora.rx.dropped
```

### 3.5 Evidence

```
evidence.claim.asserted
evidence.claim.attested
evidence.dispute.opened
evidence.dispute.retracted
evidence.ebkh.synced
evidence.ebkh.sync_partial
```

### 3.6 Civil defense

```
civdef.alert.published
civdef.alert.forwarded
civdef.alert.acked
civdef.alert.cancelled
civdef.alert.dropped.revoked
civdef.alert.foreign_role
civdef.role.registered
civdef.role.revoked
civdef.audit.checkpointed
civdef.audit.broken
```

### 3.7 Protocol

```
protocol.descriptor.announced
protocol.registry.updated
protocol.conformance.ran
```

---

## 4. Type aliases (added to `hearthnet/types.py`)

```python
ShardID         = NewType("ShardID", str)               # "model:layer_range[:tier]"
ExpertID        = NewType("ExpertID", str)              # "human:..." | "model:..." | "service:..." | "external:..."
ExpertKind      = Literal["human","model","service","external"]
ClaimID         = NewType("ClaimID", str)               # base32 of SHA-256 canonical claim
SourceID        = NewType("SourceID", str)
EvidenceLevel   = Literal["unverified","cited","cross_referenced","attested","disputed"]
RoundID         = NewType("RoundID", str)               # ULID
LoraBeaconID    = NewType("LoraBeaconID", str)
LoraDeviceID    = NewType("LoraDeviceID", str)
AlertID         = NewType("AlertID", str)               # ULID
AlertSeverity   = Literal["info","advisory","warning","emergency","extreme"]
AckStatus       = Literal["received","acting","need_help","standing_down","mistaken"]

@dataclass(frozen=True)
class ProtocolVersion: major: int; minor: int; patch: int; suffix: str = ""

# Reused from earlier phases but referenced here for completeness:
NodeID          # M01
EventID         # X02
AuthToken       # M16
Bbox            # M07 spatial extensions
Tensor          # local LLM tensor type, dtype-tagged
```

---

## 5. Centralised constants (`hearthnet/constants.py`, Phase 3 additions)

```python
# --- Distributed inference (M26) ---
DISTRIBUTED_LLM_MAX_SHARDS_PER_PIPELINE              = 16
DISTRIBUTED_LLM_SHARD_HEARTBEAT_SECONDS              = 5
DISTRIBUTED_LLM_FAILOVER_TIMEOUT_SECONDS             = 10
DISTRIBUTED_LLM_MAX_PIPELINE_LATENCY_TOKENS_PER_S    = 2.0     # advisory floor
DISTRIBUTED_LLM_DEFAULT_DTYPE                        = "fp16"

# --- MoE routing (M27) ---
MOE_TOP_K_DEFAULT                                    = 3
MOE_LEARNED_SCORER_MIN_FEEDBACK_SAMPLES              = 200
MOE_HUMAN_HANDOFF_DEFAULT_TIMEOUT_HOURS              = 24
MOE_HUMAN_HANDOFF_COOLDOWN_HOURS                     = 2
MOE_HUMAN_RATE_LIMIT_PER_DAY                         = 5

# --- Federated learning (M28) ---
FEDLEARN_MAX_LORA_RANK                               = 64
FEDLEARN_MAX_LORA_TARGET_MODULES                     = 8
FEDLEARN_MAX_TRAIN_STEPS                             = 1000
FEDLEARN_MAX_PARTICIPANTS                            = 32
FEDLEARN_MIN_PARTICIPANTS                            = 3
FEDLEARN_DP_NOISE_SCALE_DEFAULT                      = 0.0     # off
FEDLEARN_CLIP_NORM_DEFAULT                           = 1.0
FEDLEARN_SUBMISSION_MAX_BYTES                        = 64 * 1024 * 1024

# --- LoRa beacons (M29) ---
LORA_BEACON_PERIOD_SECONDS_DEFAULT                   = 600     # 10 min
LORA_BEACON_MAX_PAYLOAD_BYTES                        = 32
LORA_RX_QUEUE_MAX                                    = 256
LORA_PEER_RX_MAX_PER_MINUTE                          = 20
LORA_PANIC_BURST_COUNT                               = 3
LORA_PANIC_BURST_GAP_MS                              = 800

# --- Evidence (M30) ---
EVIDENCE_CLAIM_TTL_DAYS_DEFAULT                      = 365
EVIDENCE_DISPUTE_MIN_TRUST                           = 0.3
EVIDENCE_MAX_PROVENANCE_DEPTH                        = 8

# --- Civil defense (M31) ---
CIVDEF_AUDIT_RETENTION_YEARS                         = 10      # operator must validate against current law
CIVDEF_ACK_MAX_PER_MINUTE_PER_NODE                   = 5
CIVDEF_ALERT_TITLE_MAX_CHARS                         = 80
CIVDEF_ALERT_BODY_MAX_CHARS                          = 1000

# --- Tensor transport (X08) ---
TENSOR_CHUNK_BYTES                                   = 1 * 1024 * 1024     # 1 MiB
TENSOR_FLOW_CONTROL_WINDOW                           = 16
TENSOR_COMPRESSION_THRESHOLD_BYTES                   = 64 * 1024
TENSOR_KEEPALIVE_SECONDS                             = 30
TENSOR_MAX_SESSION_LIFETIME_SECONDS                  = 3600

# --- Conformance suite (X09) ---
CONFORMANCE_DEFAULT_SEED                             = 0xC0FFEE
CONFORMANCE_DEFAULT_OUTPUT_DIR                       = "./conformance-report"
```

---

## 6. Error codes (Phase 3 additions)

| Code | Module | When |
|------|--------|------|
| `experimental_disabled` | shared | Capability called with the feature flag off |
| `shard_unavailable` | M26 | No replica for the required layer range |
| `shard_unreachable` | M26 | All replicas connectivity-failed |
| `pipeline_failed` | M26 | Aggregate failure of an in-flight pipeline |
| `pipeline_cancelled` | M26 | Pipeline cancelled by caller |
| `tensor_too_large` | X08 | Tensor exceeds rx_buffer_bytes_max |
| `unknown_frame_type` | X08 | Frame type outside the defined set |
| `expert_unknown` | M27 | Referenced expert is not registered |
| `expert_unavailable` | M27 | Expert known but currently outside availability window |
| `human_handoff_declined` | M27 | Human expert explicitly declined |
| `human_handoff_timed_out` | M27 | Handoff exceeded timeout without ack |
| `consent_required` | M28 | join() without explicit operator consent |
| `base_model_mismatch` | M28 | Local base model SHA differs from manifest |
| `insufficient_resources` | M28 | Estimated VRAM/disk exceeds budget |
| `delta_invalid` | M28 | Submitted state-dict fails structural validation |
| `fedlearn_aggregation_failed` | M28 | Aggregation produced NaN/Inf |
| `fedlearn_min_participants_unmet` | M28 | Round closed below quorum |
| `fedlearn_aggregator_unreachable` | M28 | Finalize attempted while coordinator offline |
| `adapter_not_found` | M28 | Fetch for unknown adapter SHA |
| `lora_hardware_unavailable` | M29 | No stick present |
| `lora_hardware_unsupported` | M29 | Adapter init failed |
| `lora_duty_cycle_exhausted` | M29 | Non-panic send with empty budget |
| `lora_peer_unknown` | M29 | Verify against unseen sender_hash |
| `lora_peer_conflict` | M29 | Verify would create conflicting binding |
| `lora_frame_malformed` | M29 | RX frame structurally invalid |
| `claim_not_found` | M30 | Reference to unknown ClaimID |
| `claim_signature_invalid` | M30 | Signature doesn't verify |
| `evidence_cycle_detected` | M30 | Derivation chain forms a cycle |
| `evidence_contradiction` | M30 | (advisory) conflicting claims on same triple |
| `ebkh_unavailable` | M30 | EBKH endpoint unreachable |
| `civdef_cert_not_owned` | M31 | Cert holder ≠ caller identity |
| `civdef_cert_invalid` | M31 | Cert expired, revoked, or signature broken |
| `civdef_cert_unrecognised` | M31 | Issuer chain doesn't reach a trust root |
| `civdef_cert_out_of_scope` | M31 | Cert lacks the requested role/region |
| `civdef_alert_not_found` | M31 | Operation on unknown AlertID |
| `civdef_alert_target_invalid` | M31 | Malformed target or outside scope |
| `civdef_audit_chain_broken` | M31 | Audit chain hash/signature mismatch |
| `civdef_role_revoked` | M31 | Op with revoked cert |
| `civdef_region_unsupported` | M31 | No region adapter loaded |
| `civdef_ack_rate_limited` | M31 | Ack rate exceeded |
| `protocol_version_unknown` | M32 | Reference to unknown protocol version |
| `protocol_suite_not_installed` | M32 | Conformance report requested without X09 |
| `protocol_descriptor_invalid` | M32 | Malformed descriptor announcement |
| `protocol_unsupported_capability` | M32 | Federation negotiates no compatible major |

---

## 7. File map (top-level)

```
hearthnet/
├── distributed_inference/       # M26
│   ├── shard.py
│   ├── orchestrator.py
│   ├── router.py
│   ├── plan.py
│   └── failover.py
├── moe/                         # M27
│   ├── router.py
│   ├── scorer.py
│   ├── expert_registry.py
│   ├── human_in_the_loop.py
│   └── feedback.py
├── fedlearn/                    # M28
│   ├── coordinator.py
│   ├── participant.py
│   ├── trainer.py
│   ├── aggregator.py
│   ├── delta.py
│   ├── privacy.py
│   └── manifest.py
├── lora/                        # M29
│   ├── service.py
│   ├── serial_bridge.py
│   ├── frame.py
│   ├── duty_cycle.py
│   ├── peer_map.py
│   └── adapters/{meshtastic,rfm95w,sx126x}.py
├── evidence/                    # M30
│   ├── service.py
│   ├── claim.py
│   ├── store.py
│   ├── query.py
│   ├── extractor.py
│   ├── ebkh_adapter.py
│   └── trust.py
├── civdef/                      # M31
│   ├── service.py
│   ├── alert.py
│   ├── role.py
│   ├── audit.py
│   ├── target.py
│   ├── ack.py
│   └── regions/nrw.py
├── protocol/                    # M32 runtime
│   ├── service.py
│   ├── registry.py
│   └── report.py
└── transport/
    └── tensor/                  # X08
        ├── session.py
        ├── frame.py
        ├── flow.py
        └── compress.py

protocol/                        # M32 spec artefacts (repo root)
├── VERSION
├── README.md
├── CHANGELOG.md
├── governance.md
├── versioning.md
├── reference-implementations.md
├── core/...
└── experimental/...

conformance/                     # X09 suite (repo root)
├── VERSION
├── runner.py
├── report.py
├── harness/...
├── suites/...
└── vectors/...
```

---

## 8. Configuration index

Each module defines its own `*Config` dataclass; all are surfaced through the global `HearthnetConfig` and read from `~/.config/hearthnet/config.toml`. Phase 3 additions:

```python
@dataclass(frozen=True)
class HearthnetConfig:
    # ... (Phase 1, Phase 2 fields) ...
    distributed_llm:   DistributedLlmConfig
    moe:               MoeConfig
    fedlearn:          FedLearnConfig
    lora:              LoraConfig
    evidence:          EvidenceConfig
    civdef:            CivDefConfig
    tensor_transport:  TensorTransportConfig
    protocol:          ProtocolConfig
```

Every Phase 3 config has `enabled: bool = False` except `protocol` (default `True`). The bus dispatcher refuses to register Phase 3 capabilities when their module's enabled flag is False.

---

## 9. Build order (recap from `00-OVERVIEW.md`)

Phase 3 has eight independent tracks A-H that can be parallelised:

```
Track A:  X09 conformance suite scaffolding  →  M32 protocol service
Track B:  M30 evidence + EBKH adapter
Track C:  M27 MoE machine experts (router, registry, scorer)
Track D:  M27 human-in-the-loop coordinator (depends on Track C base)
Track E:  M28 federated LoRA aggregation
Track F:  X08 tensor transport  →  M26 distributed inference
Track G:  M29 LoRa beacons (hardware-gated)
Track H:  M31 civil defense (depends on M30 evidence)
```

Tracks A and F unlock the most downstream work (M32 needs X09; M26 needs X08). Tracks G and H are most easily deferred if Phase 3 needs to ship a minimal cut.

---

## 10. Open-question summary

Each module spec has its own §10 with detailed open questions. The recurring themes across Phase 3:

1. **Real-world identity binding** (M28 sybil defence, M31 institutional keys, M30 EBKH trust roots, M27 human verification) — the cryptographic story is solid; the social/institutional story is the work.
2. **Adversarial robustness** (M26 byzantine shards, M28 poisoning, M30 disputed claims, M31 forged certs) — all have stub defences and known harder problems.
3. **Second implementation** (M32) — until a non-reference impl exists, conformance is performative. This is the single most important next step.
4. **Cross-Land / cross-border generalisation** (M31 regional adapter, M30 EBKH OSINT scope, M29 regulatory regions) — designed for NRW first; structures admit other regions but they're unbuilt.
5. **Resource tiers** (M26 phone-class participants, M28 hardware fairness) — heterogeneous hardware aggregation is largely unsolved.
6. **Privacy / DP calibration** (M28 noise scale, M30 sensitive claims, M29 sender hash) — defaults are conservative; tuning is operator-by-operator.

Each module also lists module-specific items. Read them.

---

*Last updated: spec set v3.0. Phase 3 specs were authored with the intent that any of M26–M31 could be cut from a shipping release without affecting Phase 1 + Phase 2 functionality. M32 + X09 are the long-term durability investment and should ship even when other Phase 3 modules don't.*
