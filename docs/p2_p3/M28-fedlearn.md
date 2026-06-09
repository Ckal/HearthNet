# M28 — Federated Learning (LoRA Aggregation)

**Spec version:** v3.0 — *experimental*
**Depends on:** [M03 Capability Bus](../../modules/M03-capability-bus.md), [M04 LLM](../../modules/M04-llm.md), [M14 Federation](../../phase-2/modules/M14-federation.md), [X02 Event Log](../../cross-cutting/X02-events.md), [M16 Tokens](../../phase-2/modules/M16-tokens.md), [X06 WebSocket](../../phase-2/cross-cutting/X06-websocket.md)
**Depended on by:** nothing in MVP — opt-in research feature

---

## 1. Responsibility

Federated learning of small **LoRA adapters** on top of a shared base model. Each node trains locally on its own data, sends only the **adapter weight deltas** (not raw data, not full weights) to an aggregator, and receives back an averaged adapter that subsequent nodes can use or further refine.

The bet: a 3B-parameter base model with a *community-tuned* LoRA adapter ("how people in our village actually phrase things, what jargon our Feuerwehr uses, what the local agricultural calendar looks like") is more useful for the community than a generic 3B model, and we can do this without any node ever shipping its private data off-box.

This module deliberately stays at LoRA scope only. Full fine-tunes, distillation, and continual pre-training are explicitly out — both because they are bandwidth-hostile and because the privacy story for full-weight federation is significantly harder.

---

## 2. Non-goals

- **Federating raw data.** Never. Training data stays on the node that owns it.
- **Full fine-tunes.** LoRA only. If a use case truly needs more, that's a different research project.
- **Cross-base-model aggregation.** All participants in a round must run the same base model at the same quantisation. Heterogeneous aggregation is open research.
- **Mandatory participation.** Every node decides per-round whether to join. There is no "you must contribute back" rule.
- **Aggregator centralisation.** Any node can host an aggregator. There is no privileged aggregator role.
- **Hiding participation.** Whether you joined a round is visible to other participants in that round; only your data and your gradients are private.

---

## 3. File layout

```
hearthnet/fedlearn/
├── __init__.py
├── coordinator.py        # Orchestrates a round: announce, gather, aggregate, distribute
├── participant.py        # Local-side: respond to round announcements, train, submit
├── trainer.py            # Wraps M04 LLM in a LoRA training loop (peft + bitsandbytes)
├── aggregator.py         # FedAvg with optional secure aggregation
├── delta.py              # Serialise/deserialise LoRA deltas (state-dict subset)
├── privacy.py            # Optional DP-noise injection and gradient clipping
└── manifest.py           # Round manifest: base model id, hyperparams, signature
```

---

## 4. Public API

### 4.1 Dataclasses

```python
RoundID = NewType("RoundID", str)        # ULID

@dataclass(frozen=True)
class RoundManifest:
    round_id:        RoundID
    coordinator:     NodeID
    base_model_id:   str                  # exact model id from M04 ("qwen2.5:3b-instruct-q4_K_M")
    base_model_sha:  str                  # SHA-256 of base weights; mismatch = exclusion
    lora_target_modules: tuple[str, ...]  # which linear layers carry LoRA (e.g. "q_proj","v_proj")
    lora_rank:       int                  # 4 ≤ r ≤ FEDLEARN_MAX_LORA_RANK
    lora_alpha:      int
    lora_dropout:    float
    train_steps:     int                  # max local SGD steps per participant
    learning_rate:   float
    batch_size:      int
    seed:            int                  # for deterministic init of LoRA matrices
    dp_noise_scale:  float                # 0.0 = off
    clip_norm:       float                # gradient clip; must be > 0 if DP on
    min_participants: int                 # round aborts if fewer participants submit
    max_participants: int
    deadline:        datetime             # UTC; submissions after this dropped
    topic:           str                  # free-form: "niederrhein-emergency", "village-chat"
    consent_text:    str                  # human-readable; participant must accept
    coordinator_sig: bytes                # detached Ed25519 over the manifest

@dataclass
class ParticipantSubmission:
    round_id:        RoundID
    participant:     NodeID
    delta_bytes:     bytes                # serialised LoRA state-dict
    delta_sha:       str
    num_samples:     int                  # for weighted FedAvg
    train_loss:      float                # for telemetry only
    submitted_at:    datetime
    signature:       bytes                # Ed25519 over (round_id, participant, delta_sha, num_samples)

@dataclass
class RoundResult:
    round_id:        RoundID
    aggregated_delta_sha: str
    n_participants:  int
    total_samples:   int
    aggregator:      NodeID
    completed_at:    datetime
    manifest_sha:    str
    download_url:    str                  # capability bus uri for fetching the aggregated delta
```

### 4.2 Capabilities

```python
async def fedlearn_round_announce(manifest: RoundManifest) -> RoundID
async def fedlearn_round_list(topic: str | None = None) -> list[RoundManifest]
async def fedlearn_round_join(round_id: RoundID, consent: bool) -> JoinReceipt
async def fedlearn_round_submit(submission: ParticipantSubmission) -> SubmitReceipt
async def fedlearn_round_status(round_id: RoundID) -> RoundStatus
async def fedlearn_round_finalize(round_id: RoundID) -> RoundResult     # coordinator-only
async def fedlearn_adapter_fetch(sha: str) -> bytes
async def fedlearn_adapter_apply(sha: str, scope: Literal["session","node"]) -> ApplyReceipt
```

All capabilities are in the `experimental.fedlearn.*` namespace and only registered on the bus when `experimental.fedlearn = true` in the node config.

### 4.3 Coordinator class

```python
class RoundCoordinator:
    def __init__(self,
                 bus: CapabilityBus,
                 event_log: EventLog,
                 llm: LLMService,
                 fedlearn_config: FedLearnConfig): ...

    async def announce_round(self, draft: RoundManifestDraft) -> RoundID: ...
    async def collect_submissions(self, round_id: RoundID) -> list[ParticipantSubmission]: ...
    async def aggregate(self, round_id: RoundID) -> bytes: ...
    async def finalize_and_publish(self, round_id: RoundID) -> RoundResult: ...

    # internal
    async def _validate_submission(self, sub: ParticipantSubmission, manifest: RoundManifest) -> None: ...
    async def _emit(self, evt: Event) -> None: ...
```

### 4.4 Participant class

```python
class RoundParticipant:
    def __init__(self,
                 bus: CapabilityBus,
                 event_log: EventLog,
                 llm: LLMService,
                 data_provider: TrainingDataProvider,
                 fedlearn_config: FedLearnConfig): ...

    async def consider_round(self, manifest: RoundManifest) -> Decision: ...
    async def train(self, manifest: RoundManifest) -> ParticipantSubmission: ...
    async def submit(self, submission: ParticipantSubmission) -> SubmitReceipt: ...
    async def apply_aggregated(self, result: RoundResult, scope: Literal["session","node"]) -> ApplyReceipt: ...
```

### 4.5 Aggregator

```python
class FedAvgAggregator:
    def __init__(self, manifest: RoundManifest): ...

    def add(self, submission: ParticipantSubmission, delta: dict[str, Tensor]) -> None: ...
    def aggregate(self) -> dict[str, Tensor]: ...      # weighted by num_samples

class SecureFedAvgAggregator(FedAvgAggregator):
    """Optional: pairwise masking so the aggregator sees only the sum, never individual deltas."""
    def __init__(self, manifest: RoundManifest, mask_scheme: Literal["additive_pairwise"] = "additive_pairwise"): ...
```

### 4.6 Privacy helpers

```python
def clip_gradient(state_dict: dict[str, Tensor], max_norm: float) -> dict[str, Tensor]
def add_dp_noise(state_dict: dict[str, Tensor], scale: float, rng: Generator) -> dict[str, Tensor]
def epsilon_estimate(scale: float, clip: float, n_steps: int, batch: int, dataset_size: int) -> float
```

---

## 5. Behaviour

### 5.1 Round lifecycle

```
ANNOUNCED ──join──▶ JOINED ──train──▶ TRAINED ──submit──▶ SUBMITTED ──┐
   │                                                                  │
   │                              ┌──────────── aggregate ◀───────────┘
   │                              ▼
   └────deadline reached────▶ AGGREGATING ──finalize──▶ COMPLETED
                                                  │
                                                  └──min_participants not met──▶ ABORTED
```

State transitions are recorded as events (`fedlearn.round.*`) on the coordinator's event log. Participants see their own state mirrored via subscription.

### 5.2 Manifest signing

Manifest is canonicalised (JCS, like federation manifests in M14 §5.2), then signed Ed25519 by the coordinator's node key. Participants must verify the signature before training. A manifest with an invalid signature is dropped silently and logged as a security event (`security.signature.invalid`).

### 5.3 Consent flow

When `fedlearn.round.join` is called, the participant module must:

1. Check `experimental.fedlearn` is enabled in node config. If not → `experimental_disabled`.
2. Display `manifest.consent_text` to the operator via the M11 Notifications path. The operator must explicitly accept. The acceptance is stored as a signed `fedlearn.consent.granted` event.
3. Verify coordinator signature. If invalid → `signature_invalid` (we deliberately don't say *whose* signature; bystanders learn nothing useful).
4. Check `base_model_sha` against the locally-installed base model. If mismatch → `base_model_mismatch`. Do not download a different base on demand; this is a hard error.
5. Check resource budget: estimate VRAM and disk for the training run from `lora_rank * len(target_modules) * hidden_size`. If insufficient → `insufficient_resources`.
6. If all checks pass → emit `fedlearn.round.joined`, return `JoinReceipt`.

### 5.4 Local training

The trainer wraps M04's LLM handle in a HuggingFace `peft.LoraConfig` and uses `bitsandbytes` 4-bit base + fp16 LoRA matrices. Training data is provided by an injected `TrainingDataProvider` — the module never reaches into other modules' storage. Typical providers:

- `ChatHistoryProvider` (asks M10 for redacted, consented chat turns),
- `KBProvider` (asks M07 for documents tagged for training),
- `CustomFileProvider` (operator-curated training set).

After `train_steps` steps or convergence (loss plateau over a window), the trainer extracts the LoRA state-dict, applies optional gradient clipping and DP noise (if `manifest.dp_noise_scale > 0`), serialises, signs, and returns a `ParticipantSubmission`.

### 5.5 Aggregation

The default aggregator is weighted **FedAvg**: each adapter weight is weighted by `num_samples` and averaged across submissions. After aggregation, the coordinator emits `fedlearn.round.aggregated` and stores the aggregated delta via the capability bus (using the same content-addressed file path that M06 Files uses).

If the round was declared with `secure=true` in the draft, `SecureFedAvgAggregator` is used: each participant pair establishes an additive mask, masks cancel in the sum, and the aggregator never sees individual deltas. This costs an extra round-trip between participants before submission (the *mask exchange phase*) and requires `min_participants ≥ 3`.

### 5.6 Distribution

The aggregated adapter is published as a content-addressed file. Participants who joined the round get a `fedlearn.round.completed` event with the SHA. They can choose to:

- **Session apply** — load into a single LLM session via M04 (`llm.session.apply_adapter`),
- **Node apply** — install as the default adapter for the node (requires explicit operator action),
- **Discard** — do nothing.

Non-participants can also fetch and apply adapters they trust. There is no DRM and no whitelist: the aggregated delta is just a file with a SHA.

### 5.7 Failure modes

- **Coordinator vanishes mid-round:** participants wait until `deadline`, then any participant can call `fedlearn.round.finalize_takeover(round_id)` which constructs the aggregated delta from received submissions and re-publishes. The takeover is signed by the takeover-node and is visible as such.
- **A participant submits garbage:** validation in `_validate_submission` checks tensor shapes, dtypes, finite-ness (no NaN/Inf), and that the delta is structurally a valid LoRA state-dict for the manifest's `lora_target_modules`. Garbage submissions are dropped and logged.
- **Sybil flooding:** all participants must be authenticated with M01 identity and the manifest can require a minimum reputation/trust score (this is open research — for v3.0 the field exists in the manifest but is not yet enforced).
- **Adversarial gradient (poisoning):** out of scope for v3.0; documented in Open Research Questions §10.

---

## 6. Errors

| Code                            | When                                                                |
|---------------------------------|---------------------------------------------------------------------|
| `experimental_disabled`         | Caller invokes a fedlearn capability with the flag off              |
| `signature_invalid`             | Manifest or submission signature does not verify                    |
| `base_model_mismatch`           | Local base model SHA differs from manifest                          |
| `insufficient_resources`        | Estimated VRAM/disk exceeds budget                                  |
| `consent_required`              | join() called without an explicit consent record                    |
| `round_full`                    | `max_participants` reached                                          |
| `round_closed`                  | Submission after deadline                                           |
| `delta_invalid`                 | Submitted state-dict fails structural validation                    |
| `fedlearn_aggregation_failed`   | Aggregation produced NaN/Inf or insufficient submissions            |
| `fedlearn_min_participants_unmet` | Round closes with fewer than `min_participants` valid submissions |
| `fedlearn_aggregator_unreachable` | finalize() called while coordinator is offline and takeover not triggered |
| `adapter_not_found`             | `fedlearn.adapter.fetch` for an unknown SHA                         |

---

## 7. Configuration

```python
@dataclass(frozen=True)
class FedLearnConfig:
    enabled:                   bool = False               # master switch; default off
    max_lora_rank:             int  = FEDLEARN_MAX_LORA_RANK              # 64
    max_lora_target_modules:   int  = FEDLEARN_MAX_LORA_TARGET_MODULES    # 8
    max_train_steps:           int  = FEDLEARN_MAX_TRAIN_STEPS            # 1000
    max_round_participants:    int  = FEDLEARN_MAX_PARTICIPANTS           # 32
    min_round_participants:    int  = FEDLEARN_MIN_PARTICIPANTS           # 3
    dp_noise_scale_default:    float = FEDLEARN_DP_NOISE_SCALE_DEFAULT    # 0.0 (off)
    clip_norm_default:         float = FEDLEARN_CLIP_NORM_DEFAULT         # 1.0
    submission_max_bytes:      int  = FEDLEARN_SUBMISSION_MAX_BYTES       # 64 MiB
    require_secure_aggregation: bool = False
    auto_apply_aggregated:     bool = False               # never auto-apply by default
    training_vram_budget_mb:   int  = 8192
    training_disk_budget_mb:   int  = 4096
```

All `FEDLEARN_*` constants live in `hearthnet/constants.py` so a single source of truth governs both validation and documentation generation.

---

## 8. Tests

### 8.1 Unit

- `test_manifest_canonicalisation_stable` — re-encoding does not change SHA.
- `test_manifest_signature_roundtrip`.
- `test_delta_serialisation_roundtrip` — tensors preserve dtype and shape.
- `test_fedavg_weighted_arithmetic` — manually averaged deltas match aggregator output to within fp16 noise.
- `test_dp_noise_zero_is_identity` — `add_dp_noise(d, scale=0.0)` is a no-op.
- `test_clip_gradient_norm` — post-clip norm ≤ `max_norm`.
- `test_secure_aggregation_masks_cancel` — sum of masks across all pairs is zero.

### 8.2 Property

- Across random shapes, `fedavg([d, d, d]) == d`.
- Across random submissions, `fedavg(submissions)` is finite when all inputs are finite.

### 8.3 Integration

- Two-node loopback round on a 0.5B base model: announce → join → train (synthetic data, 10 steps) → submit → aggregate → apply. Aggregated adapter must be loadable and must not blow up perplexity by more than 2x on a held-out set (sanity, not quality).
- Coordinator-failure round: simulate coordinator going offline after submissions received; takeover by another participant produces an aggregated delta with the same SHA.
- Sybil-defence stub: round with `min_participants=3` and only 2 valid submissions aborts with `fedlearn_min_participants_unmet`.

### 8.4 Negative

- Wrong base SHA → `base_model_mismatch`.
- Submission with NaN in one tensor → `delta_invalid`.
- Submission missing one of the target modules → `delta_invalid`.
- Manifest signed by an untrusted identity → `signature_invalid`.
- Disabled flag → `experimental_disabled` even for read-only queries.

---

## 9. Cross-references

- **Phase 1 M04 LLM** — provides the local model handle, exposes `llm.session.apply_adapter` and `llm.adapter.list`.
- **Phase 1 M07 Knowledge Base** — `KBProvider` reads tagged documents for training.
- **Phase 2 M14 Federation** — federated rounds across communities use the federation transport for manifest distribution and submission. Cross-community rounds require both communities' DPOs to sign the round consent.
- **Phase 2 M16 Tokens** — round participation tokens (`fedlearn-participant` scope) are issued by the coordinator and bound to a single round.
- **Phase 2 M25 Group Chat** — `village-chat` rounds typically draw training data from group chat history (consented turns only).
- **Phase 3 M30 Evidence/EBKH** — aggregated adapters can be tracked as claims in the evidence graph; "adapter X improved perplexity on held-out set Y" is a `claim.assert`.

---

## 10. Open research questions

1. **Gradient poisoning defence.** Coordinated malicious participants can submit deltas that, when aggregated, degrade or backdoor the adapter. Median-based aggregation (Krum, trimmed mean) is a partial defence; an authenticated-data attestation (per-submission proof that gradients were computed on real, non-cherry-picked data) is the harder question. v3.0 ships FedAvg only; v3.1 may add Krum behind a flag.

2. **Heterogeneous base models.** Today, every participant in a round must run the same base model at the same quantisation. Cross-base aggregation (e.g., projecting LoRA from Qwen-3B-Q4 to Qwen-3B-Q5 or even Qwen-3B → Qwen-7B) is open. The naive approach (re-projecting via a translation matrix learnt from a calibration set) loses accuracy quickly.

3. **Adaptive DP-noise.** Fixed `dp_noise_scale` is crude. Per-round noise calibration as a function of `min_participants` and `lora_rank` would tighten the privacy/utility tradeoff. Out of scope for v3.0.

4. **Reputation-weighted FedAvg.** Weighting submissions by `num_samples * trust_score` instead of `num_samples` alone. Requires a credible trust signal, which the broader HearthNet design has not yet committed to.

5. **Continual rounds.** Today each round produces a stand-alone adapter. Stacking rounds (round N tunes on top of round N-1's aggregate) raises questions about drift, fairness, and rollback. Probably belongs in a future M28b.

6. **Cross-task adapters.** A `niederrhein-emergency` adapter and a `village-chat` adapter are trained separately. Whether they can be cleanly combined at inference time (LoRA composition) is a known-hard problem and explicitly not promised here.

7. **Hardware-class fairness.** A round held by a participant with an RTX 5090 might exclude phone-class participants by setting `train_steps` too high. A "ranked tier" with separate aggregations per tier is one possibility. Currently the manifest is a single-tier flat artefact.

8. **Audit of training data.** Even though raw data never leaves the node, the *fact that training happened on consented data* is currently un-auditable from the outside. A future zero-knowledge attestation of "this delta was computed on N samples each tagged training=true" would be useful. Out of scope.

---

*Last updated: spec v3.0.*
