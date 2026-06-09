# X07 — Federated Metrics

**Spec version:** v2.0
**Depends on:** [X03 Observability](../../cross-cutting/X03-observability.md), [M14 Federation](../modules/M14-federation.md), [M16 Tokens](../modules/M16-tokens.md), [X04 Config](../../cross-cutting/X04-config.md)
**Depended on by:** Operator dashboards (out of band), federation health UI

---

## 1. Responsibility

Take the per-node Prometheus metrics produced by [X03](../../cross-cutting/X03-observability.md) and aggregate them, with consent, into a community-level view — and, where federation grants it, into a federation-level view.

X03 gives each node a private view of itself. X07 gives:

- **The community founder** a dashboard like "how healthy is the mesh today, where are the hot spots, what's the GPU saturation across all anchors?"
- **A federated peer** a much narrower view — opt-in, aggregated, no per-node identifiers — like "Geldern reports 18 active members and 4.2k events/day".

The design rule is: **less information at greater distance**. Per-node detail stays on the node. The community sees aggregates. Federated peers see anonymised aggregates. There is no global "every node and what it does" surface.

---

## 2. File layout

```
hearthnet/observability/
├── federated.py              # FederatedMetricsExporter & Aggregator
├── otlp_export.py            # Optional OpenTelemetry OTLP push
├── aggregation_views.py      # SQL-like views over time-series
└── consent.py                # Per-metric publish consent
```

---

## 3. Public API

### 3.1 `FederatedMetricsExporter`

```python
class FederatedMetricsExporter:
    """
    Pulls metrics from the local Prometheus registry, applies consent rules,
    and publishes aggregated subsets either:
      - to the community's aggregator anchor (mesh-internal)
      - to an external OTLP collector (optional, off by default)
      - to federated peers via the bus
    """

    def __init__(
        self,
        observability:   Observability,
        consent:         ConsentPolicy,
        bus:             CapabilityBus,
        settings:        FederatedMetricsSettings,
    ): ...

    async def start(self) -> None: ...
    async def stop(self) -> None: ...

    # Triggered by tick; publishes to internal bus topic
    async def publish_community(self) -> None: ...

    # Triggered when federated peer requests
    async def publish_federated(self, peer_community_id: NodeID) -> AggregatedSnapshot: ...

    # OTLP push, off by default
    async def push_otlp(self, endpoint: str) -> None: ...
```

### 3.2 `MetricsAggregator`

Runs on the **aggregator anchor** (any anchor designated by community policy; default is the founder's node):

```python
class MetricsAggregator:
    """
    Subscribes to `observability.metrics.tick.*` events from all members,
    keeps a 7-day rolling window, exposes:
      - GET /metrics/community   (Prometheus format, community-wide)
      - capability `observability.community_snapshot@1.0`
    """

    def __init__(self, bus: CapabilityBus, event_log: EventLog, store: TimeSeriesStore): ...

    async def start(self) -> None: ...

    async def community_snapshot(self) -> CommunityMetrics: ...
    async def federated_snapshot(self, peer_id: NodeID) -> AggregatedSnapshot: ...
```

### 3.3 Snapshot dataclasses

```python
@dataclass
class NodeMetricsTick:
    """What each node publishes every METRICS_TICK_SECONDS (default 60)."""
    node_id:            NodeID
    timestamp:          datetime
    cpu_pct:            float
    mem_used_mb:        int
    mem_total_mb:       int
    gpu_pct:            float | None
    gpu_mem_used_mb:    int | None
    disk_used_gb:       float
    disk_total_gb:      float
    capability_calls_per_min: dict[str, int]  # by capability
    error_rate_per_min:       dict[str, float]
    p95_latency_ms_by_cap:    dict[str, float]
    online_seconds:     int                    # since last restart

@dataclass
class CommunityMetrics:
    """Aggregated over the community.  Has per-node detail (members see members)."""
    timestamp:           datetime
    nodes_total:         int
    nodes_online:        int
    nodes:               list[NodeMetricsTick]
    capability_calls_per_min_total: dict[str, int]
    events_per_min:      int
    storage_used_gb:     float
    federation_links:    int

@dataclass
class AggregatedSnapshot:
    """For federated peers.  No per-node detail, no identifiers, banded values."""
    timestamp:                    datetime
    community_id:                 NodeID
    nodes_online_band:            str             # "10-20", "20-50", etc.
    daily_active_members_band:    str
    capability_calls_per_day_top: list[tuple[str, str]]   # [(cap, band)]
    error_rate_band:              str
    federation_links_count:       int
```

### 3.4 `ConsentPolicy`

```python
@dataclass
class ConsentPolicy:
    """
    Loaded from policy.yaml.  Controls what leaves the node.
    """
    publish_to_community:  set[str]   # metric names included in NodeMetricsTick
    publish_to_federated:  set[str]   # subset, applied to AggregatedSnapshot
    publish_to_external:   bool       # OTLP push on/off
    aggregation_min_nodes: int        # don't expose a metric unless ≥ N nodes contribute
    banding:               dict[str, list[int]]  # metric → bucket edges
```

---

## 4. Behaviour

### 4.1 Tick lifecycle

Every `METRICS_TICK_SECONDS` (default 60s) each node:

1. Snapshots its local Prometheus registry.
2. Filters per `ConsentPolicy.publish_to_community`.
3. Constructs a `NodeMetricsTick`.
4. Publishes to bus topic `observability.metrics.tick.<community_id>` over WebSocket pubsub (efficient: many small messages, low latency).
5. Also writes a local rolling-window copy for debug.

The aggregator anchor subscribes to the topic, ingests into its time-series store, and computes `CommunityMetrics` on demand.

### 4.2 Aggregator selection

The community policy contains:

```yaml
observability:
  aggregator_anchor: ed25519:<NodeID>   # optional; if absent, any anchor self-elects
  aggregator_failover_seconds: 600
```

If the configured aggregator is offline for `aggregator_failover_seconds`, another anchor self-elects (lowest NodeID hash wins). A live community-wide view tolerates the aggregator going offline; nodes keep publishing ticks and a new aggregator picks up where the old one left off (with a brief gap).

### 4.3 What gets exposed to whom

| Metric category | Self | Other members | Aggregator anchor | Federated peers | External OTLP |
|------------------|------|----------------|-------------------|------------------|---------------|
| CPU / mem / GPU per-node | ✅ | per policy | ✅ | ❌ | ❌ |
| Per-capability call counts | ✅ | ✅ | ✅ | banded only | optional |
| Per-capability latencies | ✅ | aggregated | ✅ | ❌ | ❌ |
| Error rates | ✅ | aggregated | ✅ | banded only | optional |
| Federation link count | ✅ | ✅ | ✅ | exact count | ❌ |
| File counts / sizes | ✅ | ❌ | aggregated | banded | ❌ |
| Identity of which node did what | ✅ | per policy | ❌ (anonymised on ingest) | ❌ | ❌ |

The aggregator does **not** store per-node identity in its long-term time series. It computes per-node views on the fly for the founder UI but persists only anonymised aggregates after `MEMBER_DETAIL_RETENTION_HOURS` (default 24).

### 4.4 Banding

Federated snapshots use bands rather than exact numbers to prevent triangulation across multiple federations:

```yaml
banding:
  nodes_online: [0, 5, 10, 20, 50, 100, 500]
  daily_active_members: [0, 3, 10, 30, 100]
  capability_calls_per_day: [0, 100, 1000, 10000, 100000]
  error_rate: [0, 0.01, 0.05, 0.10]
```

Result: `"nodes_online_band": "10-20"` instead of `19`.

### 4.5 OTLP push (external)

Off by default. When `publish_to_external=true`:

- Pushes to a configured OTLP endpoint (could be Grafana Cloud, self-hosted Tempo/Mimir, or your own collector).
- Only metrics in `publish_to_external` set leave the node.
- The receiver gets aggregated, banded data — same restrictions as a federated peer.
- TLS required; OTLP headers carry an API token (set via env var, not in policy file).

This is the path for an operator (Christof) who wants a single Grafana dashboard across all his bofrost-managed communities — but the protections still apply: external collector cannot reconstruct who did what.

### 4.6 Trackio integration

Phase 1 already supports per-node Trackio logging. X07 adds: **the aggregator** can push a community-level summary to a Trackio space, useful for hackathon demos and HF leaderboard-style displays.

`policy.observability.trackio_community_space` (URL) is configurable. The aggregator anchor pushes `CommunityMetrics` rows hourly. Per-node detail is excluded from this path; only aggregates go.

### 4.7 Federated peer queries

A federated peer asks for our snapshot via:

```
POST /bus/v1/call
X-HearthNet-Community: <their community>
Capability: observability.federated_snapshot@1.0
Body: {"input": {"window_hours": 24}}
```

Bus checks federation scope, calls the aggregator, returns `AggregatedSnapshot`. The peer's UI may display "Geldern: 10-20 nodes online, light activity today" alongside their own community.

### 4.8 Cost & sizing

A `NodeMetricsTick` is roughly 500 bytes JSON. At 1 tick / 60s per node, a 50-node community publishes 50 × 500B / 60s ≈ 420 B/s on the metrics topic. Negligible.

The aggregator's time-series store is **DuckDB** (Phase 2 choice; SQLite would also work). Retention: 7 days at full per-node resolution, then daily roll-ups for 90 days, then weekly forever.

---

## 5. Errors

| Code | Cause |
|------|-------|
| `unavailable` | Aggregator anchor offline |
| `aggregation_too_few_nodes` | < `aggregation_min_nodes` nodes contributed; refusing to disclose |
| `federation_forbidden` | Peer requested a metric category not in federation scope |
| `consent_denied` | Local policy forbids this metric from leaving the node |

---

## 6. Configuration

```toml
[observability.federated]
enabled                        = true
metrics_tick_seconds           = 60
aggregator_failover_seconds    = 600
member_detail_retention_hours  = 24
aggregation_min_nodes          = 3
publish_to_external            = false
otlp_endpoint                  = ""
otlp_token_env                 = "OTLP_TOKEN"
trackio_community_space        = ""

[observability.federated.consent.publish_to_community]
metrics = [
  "node.cpu_pct", "node.mem_pct", "node.gpu_pct",
  "node.online_seconds", "node.capability_calls_per_min",
  "node.p95_latency_by_capability",
]

[observability.federated.consent.publish_to_federated]
metrics = [
  "community.nodes_online", "community.daily_active_members",
  "community.capability_calls_top", "community.federation_links",
]

[observability.federated.consent.banding]
"community.nodes_online"          = [0, 5, 10, 20, 50, 100]
"community.daily_active_members"  = [0, 3, 10, 30, 100]
"community.capability_calls_top"  = [0, 100, 1000, 10000]
"community.error_rate"            = [0, 0.01, 0.05, 0.10]
```

---

## 7. Tests

### 7.1 Unit
- Banding: value 17 with bands `[0,5,10,20,50]` returns `"10-20"`
- Aggregation refuses when contributors < min: `aggregation_too_few_nodes`
- Consent: a metric not in `publish_to_community` set is excluded from tick
- AggregatedSnapshot construction strips all NodeID fields

### 7.2 Integration
- 5 nodes publish ticks for 5 minutes; aggregator's snapshot reflects 5 contributors with correct totals
- Aggregator kill / failover: a second anchor takes over within 10 minutes, snapshot resumes
- Federated peer requests snapshot; receives banded version; cannot infer specific node counts

### 7.3 Adversarial
- Malicious node publishes inflated counters → outlier detection drops obvious outliers (>3σ) from the aggregate
- Federated peer requests snapshot for window the aggregator hasn't filled → `aggregation_too_few_nodes`
- OTLP endpoint compromised: leaked data contains only banded aggregates; per-node attribution impossible

### 7.4 Privacy
- Asserts: no NodeID, IP, or device-identifying string is present in `AggregatedSnapshot`
- Asserts: after `MEMBER_DETAIL_RETENTION_HOURS` the aggregator's persisted store contains no per-node rows

---

## 8. Cross-references

- Capability: `observability.community_snapshot@1.0`, `observability.federated_snapshot@1.0` (introduced here, listed in [CAPABILITY_CONTRACT_v2 §3](../CAPABILITY_CONTRACT_v2.md#3-complete-new-capabilities-list))
- Bus topic: `observability.metrics.tick.<community_id>`
- Underlying primitives: [X03](../../cross-cutting/X03-observability.md)
- Federation scope: [M14 §5](../modules/M14-federation.md)
- Policy schema: [X04](../../cross-cutting/X04-config.md)

---

## 9. Open questions

1. **Differential privacy** — adding Laplacian noise to federated snapshots. Worth it for stronger guarantees, or does banding already suffice given small N?
2. **Federation gossip of snapshots** — should snapshots propagate transitively (A→B→C sees A's banded numbers), or strictly point-to-point? Phase-2 default: point-to-point.
3. **Per-capability cost accounting** — exposing GPU-seconds per capability call would help operators reason about cost / who's consuming what. Reveals usage patterns; needs consent design.
4. **Histogram vs banded scalars** — banded scalars are simple but lose distribution shape. Full Prometheus histograms with aggregated buckets might be a better federated unit. Trade-off: bytes on the wire vs richness.
5. **Aggregator beyond a single anchor** — at large scale (100+ nodes) a single aggregator becomes a bottleneck. Sharded aggregation (per-capability-prefix?) is a Phase-3 problem.
