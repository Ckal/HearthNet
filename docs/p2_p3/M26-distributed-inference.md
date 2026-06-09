# M26 — Distributed Inference

**Spec version:** v3.0 — *experimental*
**Depends on:** [X08 Tensor Transport](../cross-cutting/X08-tensor-transport.md), [X06 WebSocket](../../phase-2/cross-cutting/X06-websocket.md), [M04 LLM](../../modules/M04-llm.md), [M16 Tokens](../../phase-2/modules/M16-tokens.md), [X03 Observability](../../cross-cutting/X03-observability.md)
**Depended on by:** Optional `experimental.distributed_llm.chat` backend in M04

---

## 1. Responsibility

Run a single LLM forward pass across multiple machines on the same LAN (or, in extremely careful setups, a single federation). Take a 7B model that doesn't fit on any one anchor's GPU and split it: anchor A holds layers 0–7, anchor B holds 8–15, anchor C holds 16–23, etc. A request orchestrator chains them and streams tokens back to the user.

This is a **research module**. It exists for two reasons:

1. **Resilience.** When a community's biggest GPU breaks, the next-biggest fleet of GPUs can still serve mid-sized models cooperatively.
2. **Reach.** A community of three households, each with consumer hardware, can collectively run a model none of them could run alone.

It is explicitly **not** for serving production user-facing LLM traffic at scale. The latency is worse than local inference (typically 2–4× per token), the orchestration is fragile (one shard offline = retry the whole pipeline), and the GPU memory savings come at significant complexity cost. Communities should default to local inference; this module exists for the cases where local isn't enough.

---

## 2. Non-goals (loud and clear)

- **Large models.** 70B-class models are out of scope. The math says you'd need ten 24 GB GPUs to host one, which is the wrong problem for a neighbourhood mesh to solve.
- **Cross-WAN sharding.** Inference across the public internet is uneconomical (latency, bandwidth). Limit to same LAN or same-VPN federation.
- **Heterogeneous shards across model versions.** All shards in a pipeline must serve the **exact same model and weights checksum**. No partial-model recovery.
- **Replacing local inference.** When `policy.research.enable = false`, this module is inert.

---

## 3. File layout

```
hearthnet/distributed_inference/
├── __init__.py
├── shard.py              # Shard, ShardDescriptor, ShardServer
├── pipeline.py           # Pipeline, PipelineOrchestrator
├── routing.py            # Picks a set of shards that cover [0..N] layers
├── health.py             # Heartbeats, failover detection
└── backends/
    ├── base.py
    ├── petals_like.py    # uses bigscience/petals client/server primitives
    └── small_model_layered.py  # custom impl for small models (≤ 3B)
```

---

## 4. Public API

### 4.1 Dataclasses

```python
@dataclass(frozen=True)
class ShardDescriptor:
    shard_id:        ShardID         # "<model_id>:<lo>-<hi>"
    model_id:        str             # HF model id
    weights_sha256:  str             # full model weights hash; shards must match
    layer_range:     tuple[int,int]  # inclusive
    vram_required_mb: int
    max_concurrent_streams: int
    host:            NodeID
    endpoint:        Endpoint        # ws://...
    advertised_at:   datetime

@dataclass
class Pipeline:
    pipeline_id:     str
    model_id:        str
    weights_sha256:  str
    total_layers:    int
    ordered_shards:  list[ShardDescriptor]
    established_at:  datetime

@dataclass
class ShardHealth:
    shard_id:        ShardID
    online:          bool
    last_seen:       datetime
    p95_latency_ms:  float
    queue_depth:     int
```

### 4.2 `ShardServer`

```python
class ShardServer:
    """Hosts one contiguous shard.  Loaded on demand; lazy-evictable under memory pressure."""

    def __init__(self, descriptor: ShardDescriptor, model_loader: ModelLoader, settings: ShardSettings): ...

    async def start(self) -> None:
        # Load weights for the layer range; register `experimental.distributed_llm.shard.serve` on the bus
        ...

    async def forward(self, activations_in: TensorChunkStream) -> TensorChunkStream:
        """The hot path.  Receives activations, runs layers, emits activations."""
        ...

    async def health(self) -> ShardHealth: ...

    async def evict(self) -> None:
        """Free VRAM; triggered by host memory manager."""
        ...
```

### 4.3 `PipelineOrchestrator`

```python
class PipelineOrchestrator:
    """
    Chooses shards to cover the model's layers, opens streams to each, and
    pumps activations through them in order.  Handles failover.
    """

    def __init__(
        self,
        bus:           CapabilityBus,
        router:        ShardRouter,
        health:        ShardHealthTracker,
        observability: Observability,
    ): ...

    async def chat(
        self,
        request:  LlmChatRequest,
        params:   DistributedChatParams,
    ) -> AsyncIterator[StreamFrame]:
        # 1. Resolve a Pipeline covering all layers of the target model
        # 2. Open WS streams to each shard via X08 tensor transport
        # 3. For each token step:
        #    embedding → shard 0 → shard 1 → ... → shard N → token sample
        # 4. Yield `token_delta` frames; emit `shard_status` and `shard_failover` diagnostics
        # 5. On any shard failure, attempt re-routing once; if that fails and
        #    `params.fallback_to_local`, fall back to local inference and emit a
        #    `pipeline_aborted` frame
        ...
```

### 4.4 `ShardRouter`

```python
class ShardRouter:
    """
    Given a model_id and an `experimental.shard.advertised` event stream,
    pick a covering set of shards minimising:
      - total network hops
      - max per-shard queue depth
      - chance of overlap with the caller's own GPU (avoid self-as-shard)
    """

    def __init__(self, store: ShardStore, settings: RoutingSettings): ...

    async def pick(self, model_id: str, weights_sha256: str) -> Pipeline: ...
    async def repick(self, pipeline: Pipeline, exclude: set[ShardID]) -> Pipeline: ...
```

---

## 5. Behaviour

### 5.1 Shard advertisement and discovery

A node hosting a shard emits `experimental.shard.advertised` events into the community event log. The event carries `ShardDescriptor` fields plus a timestamp. Advertisements expire after `DISTRIBUTED_SHARD_HEALTH_TIMEOUT_S * 4` (default 120s); shard hosts must re-advertise via heartbeat.

When a node opts out (`policy.research.enable=false`), it does not emit advertisements. Existing advertisements expire normally.

The shard store is a local read model built from these events, indexed by `(model_id, weights_sha256, layer_range)`.

### 5.2 Pipeline construction

`ShardRouter.pick`:

1. Filter advertisements to those matching `model_id` and `weights_sha256`.
2. Greedy cover: starting from layer 0, pick the shard with the lowest queue depth that includes the next uncovered layer; advance the cursor; repeat. Returns failure if any layer is uncoverable.
3. Prefer shards on the same LAN if possible (LAN advertisements have a lower "hop weight" metric attached by Discovery).
4. Avoid sharding to **self** as the first shard — embedding + sampling should stay on the orchestrator.

Constructed pipelines are not persisted; they're per-call.

### 5.3 Forward pass

Per token:

```
[orchestrator] embedding → [shard 0] layers 0..7 → [shard 1] layers 8..15 → ... → [orchestrator] sample
```

Activations flow as **fp16 tensors** by default (configurable to fp32 for debugging). Each hop is a WebSocket binary frame stream (see [X08](../cross-cutting/X08-tensor-transport.md)). The orchestrator interleaves token-N and token-N+1: as soon as shard 0 finishes token N, the orchestrator pushes token N+1's embedding into shard 0 while shard 1 is still processing N. This pipeline parallelism approaches the latency of the longest-latency shard at steady state.

### 5.4 Failure handling

If a shard's stream errors or stalls past `DISTRIBUTED_SHARD_HEALTH_TIMEOUT_S`:

1. The orchestrator emits a `shard_status` frame with `status:"degraded"`.
2. Calls `router.repick(pipeline, exclude={failed_shard_id})`.
3. If repick succeeds, opens a fresh stream to the replacement and emits `shard_failover` frame. **In-flight tokens are restarted** (no mid-token recovery).
4. If repick fails and `params.fallback_to_local`, the orchestrator silently restarts the call as a local-only `llm.chat@2.0` against any local model that matches.
5. Else: emit `pipeline_aborted` frame and return `shard_unavailable`.

`DISTRIBUTED_FALLBACK_TO_LOCAL_AFTER_FAILURES` (default 2): if failover happens that many times in one call, give up and fall back to local.

### 5.5 Streaming and backpressure

Tensor-chunk streams use a window of `TENSOR_FLOW_CONTROL_WINDOW` chunks (default 16). Each chunk is at most `TENSOR_CHUNK_BYTES` (1 MB). If the downstream shard's send queue fills, the orchestrator pauses upstream until ACKs drain. See [X08 §4](../cross-cutting/X08-tensor-transport.md).

### 5.6 Concurrency

A shard's `max_concurrent_streams` is honoured strictly. If the orchestrator's call would exceed it, the orchestrator picks a different shard (via `router.repick`) rather than queuing.

A shard's GPU memory budget is enforced by the shard host's own resource manager; a shard exceeding its budget gets evicted and re-advertises with `vram_required_mb` updated next time it loads.

### 5.7 Models supported

Phase 3 launches with two backend choices:

| Backend | Models | Notes |
|---------|--------|-------|
| `small_model_layered` | Qwen2.5-{1.5B,3B,7B}, Llama-3.2-{1B,3B}, MiniCPM-3 | Custom HearthNet impl; PyTorch model surgery to expose per-layer forward |
| `petals_like` | (vendored from BigScience Petals) | Optional; only if user installs `hearthnet[petals]` extra |

The `small_model_layered` backend handles models up to roughly 7B parameters cleanly; beyond that the activation transport becomes the bottleneck.

### 5.8 Security boundary

A shard host receives activation tensors which **leak training data residue**. Treat activations as sensitive: do not log them, do not persist, do not retain past forward pass. Per-call signed authentication; the caller's identity is recorded in metrics but not in logs of tensor contents.

A malicious shard could degrade outputs subtly. Detection is hard in general; the orchestrator does **basic sanity checks** (norm bounds, NaN/Inf detection) but cannot detect adversarial corruption. Communities should only enable distributed inference among members they trust as much as they trust the LLM service operator.

### 5.9 Privacy threat surface

A shard sees the activations of every request routed through it. With effort, a shard host can reconstruct approximate input text (especially the prompt) from activations of intermediate layers. This is **a real concern, not a theoretical one**.

Mitigations (none perfect):
- Restrict participation to members at trust level `trusted` or higher.
- Mix activations with a small amount of noise at the orchestrator (research; not yet implemented).
- Use this module only for queries the requester would already trust the community with.

### 5.10 Observability

Per call, emit:
- `distributed_inference.pipeline_construct_ms`
- `distributed_inference.first_token_ms`
- `distributed_inference.tokens_per_second`
- `distributed_inference.shard_latency_ms{shard_id}` histograms
- `distributed_inference.failovers_total`
- `distributed_inference.fallback_to_local_total`

---

## 6. Errors

| Code | Cause |
|------|-------|
| `experimental_disabled` | `policy.research.enable=false` |
| `shard_unavailable` | No shard covers a required layer range, or all candidates are at max concurrency |
| `pipeline_stalled` | No progress within timeout |
| `weights_mismatch` | A shard's advertised `weights_sha256` differs from requested |
| `bad_request` | Unknown model, malformed pipeline params |

---

## 7. Configuration

```toml
[research.distributed_inference]
enabled                       = false
backend                       = "small_model_layered"
max_shards_per_request        = 16
shard_health_timeout_seconds  = 30
fallback_to_local             = true
activation_dtype              = "fp16"   # "fp16" | "fp32"
allow_self_as_shard           = false
max_concurrent_pipelines      = 4

[research.distributed_inference.host]
serve_shards                  = false
shard_eviction_idle_seconds   = 600
shard_max_vram_mb             = 20000
```

---

## 8. Tests

### 8.1 Unit
- ShardRouter cover algorithm: 16-layer model + 3 advertised shards (0-7, 4-11, 8-15) → picks {0-7, 8-15}, ignores overlap shard
- Sanity bounds on activations: NaN injection triggers `pipeline_stalled` (via failed health check on subsequent chunk)
- Pipeline construction with weights mismatch → `weights_mismatch`

### 8.2 Integration (LAN)
- Two-node setup, 1.5B model split as 0-7 / 8-15; happy-path tokens/sec measured; baseline single-machine inference also measured; ratio reported (expect 0.4–0.6× local)
- Shard host kill mid-stream; failover to a third node; total call still succeeds; latency penalty bounded
- Concurrent two-pipeline test on three nodes; no deadlock; per-call latency degrades < 2×

### 8.3 Adversarial
- Malicious shard returns garbage activations: orchestrator's NaN/Inf detector catches the call; metric `distributed_inference.shard_corruption_detected_total` increments; pipeline aborts
- Slowloris shard (returns one chunk per second): `pipeline_stalled` after timeout; failover succeeds

### 8.4 Performance budget
- 3B model, 2-shard pipeline, RTX 5090 + RTX 4090: ≥ 8 tokens/sec sustained
- First-token latency ≤ 800ms
- Construction-to-first-byte ≤ 500ms
- Tensor-chunk overhead per hop ≤ 25ms p95

---

## 9. Cross-references

- Capability spec: [CAPABILITY_CONTRACT_v3 §4.1–4.3](../CAPABILITY_CONTRACT_v3.md)
- Tensor transport: [X08](../cross-cutting/X08-tensor-transport.md)
- Base LLM service: [M04](../../modules/M04-llm.md)
- Trust levels: [M01](../../modules/M01-identity.md)

---

## 10. Open research questions

1. **Activation privacy.** Can we add fast-to-compute noise that preserves inference accuracy but defeats activation-inversion attacks? Cite the Geiping et al. inversion paper as the threat baseline.
2. **Mid-token recovery.** Currently a shard failure restarts the in-flight token. Could we use micro-checkpointing (every K tokens) to recover without a restart? Latency cost?
3. **Heterogeneous shards.** Could a 4090 host the early layers (heavier compute per layer) and a 3060 the later ones, while remaining balanced? Probably yes — automated load assignment is the research question.
4. **Async pipeline.** Currently the orchestrator interleaves at the token level. Could it interleave at the layer level (one shard processes token N+2 while another processes N+1) for higher throughput? In theory yes; coordination protocol unclear.
5. **Mixed local + distributed.** When the orchestrator could host some layers itself (it has a GPU), should it? When? Currently `allow_self_as_shard=false`. A heuristic that considers compute headroom would be richer.
6. **Adversarial detection.** Beyond NaN/Inf, can we cheaply detect activation tampering by comparing to a small "shadow inference" on a tiny model? Cost vs. benefit unclear.
7. **Pricing / incentive.** A shard host pays in GPU time. A community-internal token-economy is explicitly out of scope (00-OVERVIEW §8). But a *reputational* signal — "this anchor served 4000 shard-tokens this week" — could be helpful. Should it be a metric?
8. **Backend strategy.** `petals_like` vs `small_model_layered`: which delivers better quality / latency / robustness for our target models? An honest A/B is the answer.
