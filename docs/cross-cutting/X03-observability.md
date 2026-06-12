# X03 — Observability

**Spec version:** v1.0
**Depends on:** X04 (config), stdlib, prometheus_client (optional)
**Depended on by:** every module that does I/O

---

## 1. Responsibility

Provides logging, metrics, tracing, and self-diagnostics. No module imports `logging` directly; they import `get_logger(__name__)` from this module.

---

## 2. File layout

```
hearthnet/observability/
├── __init__.py        # exports: get_logger, metrics, trace, doctor
├── logging.py         # structured JSON logging
├── metrics.py         # Prometheus-compatible counters/histograms
├── tracing.py         # per-request trace IDs + ring buffer
└── doctor.py          # self-diagnostics
```

---

## 3. Logging

### 3.1 Public API

```python
# hearthnet.observability.logging

def configure(config: ObservabilityConfig) -> None:
    """Install handlers, formatters, rotation. Idempotent. Call once at startup."""

def get_logger(name: str) -> Logger:
    """Return a stdlib logger configured to emit JSON lines.
       Convention: name = module's __name__ (e.g. 'hearthnet.bus.router')."""

class JsonFormatter(logging.Formatter):
    """Renders LogRecords as one-line JSON: ts, level, logger, msg, **extras."""
```

### 3.2 Conventions

- Use `extra=` to attach structured fields: `log.info("routed", extra={"capability": "llm.chat", "to": node_id, "ms": 12})`
- Never `f"log message {variable}"` for production diagnostics; use structured fields instead
- Log levels:
  - `debug` — internal state, only useful with `--debug`
  - `info` — meaningful protocol events (manifest received, capability registered, peer joined)
  - `warning` — recoverable problem (signature failed, peer unreachable, quarantine)
  - `error` — unexpected failure (exception caught, service crash)
- Exceptions: always `log.exception("what happened", extra={...})` — captures traceback automatically
- Rate-limit noisy warnings: `RateLimitedLogger` wrapper, log at most once per second per (logger, message_key)

### 3.3 On-disk format

```json
{"ts":"2026-05-26T08:14:22.281Z","level":"info","logger":"hearthnet.bus.router","msg":"routed","trace_id":"01HXR...","capability":"llm.chat","to":"7H4G-...","ms":12}
```

One line per event. Files rotate daily at midnight UTC. Retention: `LOG_RETENTION_DAYS = 14` from constants.

---

## 4. Metrics

### 4.1 Public API

```python
# hearthnet.observability.metrics

def configure(config: ObservabilityConfig) -> None:
    """Set up registries, start the metrics endpoint if enabled."""

# Counter / histogram / gauge factory functions:
def counter(name: str, doc: str, labels: list[str] = []) -> Counter
def histogram(name: str, doc: str, labels: list[str] = [], buckets: list[float] | None = None) -> Histogram
def gauge(name: str, doc: str, labels: list[str] = []) -> Gauge

# Convenience for "everything else returns None when metrics disabled":
def disabled() -> bool
```

### 4.2 Standard metric set

```
hearthnet_requests_total{capability, result}                     counter
hearthnet_request_duration_ms{capability, quantile}              histogram
hearthnet_active_streams{capability}                             gauge
hearthnet_nodes_online{community}                                gauge
hearthnet_event_log_size{community}                              gauge
hearthnet_event_log_lamport_head{community}                      gauge
hearthnet_emergency_mode{state}                                  gauge   // 0 or 1
hearthnet_blob_storage_bytes                                     gauge
hearthnet_llm_tokens_generated_total{model, backend}             counter
hearthnet_llm_concurrent{model}                                  gauge
hearthnet_capability_health_success_rate{capability, node}       gauge
hearthnet_rate_limited_total{capability, reason}                 counter
hearthnet_signature_failures_total{reason}                       counter
```

### 4.3 Scrape endpoint

`GET /metrics` on the transport server (port 7080). Plain text, Prometheus format. No auth — same trust domain as the rest of the bus.

---

## 5. Tracing

### 5.1 Public API

```python
# hearthnet.observability.tracing

class Trace:
    trace_id:   str
    capability: str
    started_at: float       # monotonic seconds
    spans:      list[Span]

@contextmanager
def span(name: str, **extras) -> Iterator[Span]:
    """Open a sub-span on the current trace. Auto-closes."""

def new_trace(capability: str) -> Trace:
    """Start a new trace (typically at the top of a capability handler)."""

def current_trace() -> Trace | None:
    """Get the trace attached to the current asyncio task."""

def attach(trace: Trace) -> None:
    """Attach a trace to the current task. Used by transport when it receives a request with an X-HearthNet-Request-Id."""

def detach() -> None:
    """End the trace; record to the ring buffer; emit done log."""

def get_recent(n: int = 100) -> list[Trace]:
    """Return last N completed traces from the ring buffer (used by /trace endpoint)."""
```

### 5.2 Storage

Ring buffer in memory, `TRACE_RING_BUFFER = 10000` from constants. Optionally exported to OpenTelemetry in Phase 2.

### 5.3 Trace IDs are ULIDs

ULIDs are used because they sort by time and need no separate timestamp field.

---

## 6. Doctor

### 6.1 Public API

```python
# hearthnet.observability.doctor

@dataclass
class CheckResult:
    name:    str
    ok:      bool
    detail:  str
    fix:     str | None

def run_all(config: Config, bus: CapabilityBus) -> list[CheckResult]:
    """Run every check; return list of results."""

def run_one(name: str, config: Config, bus: CapabilityBus) -> CheckResult:
    """Run a single named check."""

# Each check is a registered function:
def register(name: str, check: Callable[[Config, CapabilityBus], CheckResult]) -> None
```

### 6.2 Standard checks

| Name | Verifies |
|------|----------|
| `keys_present` | Device key file exists, has 0600 permissions |
| `keys_loadable` | Keys parse as Ed25519 |
| `community_present` | Community manifest exists |
| `event_log_writable` | SQLite open and writable |
| `mdns_socket` | mDNS socket can bind |
| `udp_multicast` | UDP discovery socket can bind |
| `transport_port` | Bus port is free or owned by us |
| `at_least_one_capability` | Bus has registered ≥ 1 capability |
| `disk_space` | Free space ≥ 1 GB |
| `clock_sanity` | System clock within ±60s of HTTP-reachable anchor (only when internet up) |
| `llm_backend_reachable` | At least one LLM backend responds |
| `recent_error_rate` | Last 100 traces have < 20% error rate |

### 6.3 CLI integration

`hearthnet doctor` runs `run_all`, prints a coloured report, exits non-zero on any failure. See [M12](../modules/M12-cli.md).

---

## 7. Tests

- `test_logger_writes_json_lines` — assert each line parses as JSON with expected fields
- `test_metrics_endpoint_format` — Prometheus text format conforms
- `test_trace_context_propagation` — `attach`/`detach` round-trips across `asyncio.gather`
- `test_doctor_all_pass_on_default_config` — `run_all` returns all-OK on fresh init
- `test_doctor_keys_missing` — failure case for `keys_present`

---

## 8. References

- Config: [X04 §3](X04-config.md)
- Trace IDs propagate via [CONTRACT §5.1](../CAPABILITY_CONTRACT.md) `X-HearthNet-Request-Id`
- Bus emits trace events: [M03 §5.6](../modules/M03-bus.md)
