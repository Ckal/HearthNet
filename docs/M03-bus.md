# M03 — Capability Bus

**Spec version:** v1.0
**Depends on:** M01 (identity), X01 (transport, for outbound calls), X03 (observability), X04 (config), M02 (discovery, for peer events)
**Depended on by:** every service (M04, M05, M06, M07, M10, M11), M08 (UI calls capabilities via bus), M09 (registers nothing but reads peer state via bus), M12 (CLI inspects bus state)

This is **the** integration point. Re-read [00-OVERVIEW §2](../00-OVERVIEW.md) before changing this file.

---

## 1. Responsibility

- Maintain a registry of **capabilities**: local (offered by us) and remote (offered by other nodes)
- Validate every call against a JSON schema declared by the capability descriptor
- Route every call to the best provider via a scoring algorithm
- Track per-(node, capability) health and quarantine misbehaving providers
- Enforce per-capability concurrency limits and per-peer rate budgets (delegating to X01)
- Emit structured trace events for every call (via X03)
- Provide sticky routing for multi-turn capabilities (chat)

What the bus does **not** do:
- It does not move bytes (X01 does)
- It does not persist anything (X02 does, for events)
- It does not know any service's internals (services register themselves)

---

## 2. File layout

```
hearthnet/bus/
├── __init__.py          # exports: CapabilityBus, CapabilityDescriptor, CapabilityEntry
├── capability.py        # dataclasses: CapabilityDescriptor, CapabilityEntry, RouteRequest
├── registry.py          # Registry: local + remote capability index
├── router.py            # Router: scoring algorithm
├── health.py            # HealthTracker: rolling-window per-(node, cap) stats
├── schema.py            # SchemaValidator + schema_hash computation
└── trace.py             # TraceHook: emit standardised trace events
```

---

## 3. Public API

### 3.1 `capability.py`

```python
# hearthnet/bus/capability.py
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable, Awaitable

CapabilityName = str                # "llm.chat"
Version        = tuple[int, int]    # (1, 0)

# --- Descriptor: the full capability spec, used at registration ---

@dataclass(frozen=True)
class CapabilityDescriptor:
    """The complete contract for one capability offered by one service.
       Registered exactly once per (service, capability)."""
    name:             CapabilityName
    version:          Version             # (1, 0)
    stability:        str                 # "stable" | "beta" | "experimental"
    request_schema:   dict                # JSON Schema
    response_schema:  dict | None         # JSON Schema; None if pure stream
    stream_schema:    dict | None         # JSON Schema for stream frames; None if non-streaming
    params:           dict[str, Any]      # capability-instance params (e.g. {"model": "..."})
    max_concurrent:   int                 # per-node limit
    trust_required:   str                 # "member" | "trusted" | "anchor" | "self"
    timeout_seconds:  int                 # default deadline for this capability
    idempotent:       bool

    @property
    def version_str(self) -> str:
        """E.g. '1.0'"""

    def schema_hash(self) -> str:
        """BLAKE3 over canonical-JSON of {name, version, request_schema, response_schema, stream_schema}.
        Prefixed 'blake3:'. See CONTRACT §11."""

# --- Entry: the bus's record of one capability instance ---

@dataclass
class CapabilityEntry:
    """The bus's view of one (node, capability) pair.
       For local capabilities, node_id == self.node_id and handler != None."""
    node_id:           str                # full form
    descriptor:        CapabilityDescriptor
    is_local:          bool
    handler:           Callable | None    # only for local entries
    endpoint:          Endpoint | None    # only for remote entries
    in_flight:         int = 0
    last_seen:         float = 0.0        # monotonic seconds
    p50_latency_ms:    float = 0.0
    p99_latency_ms:    float = 0.0
    success_rate:      float = 1.0        # rolling HEALTH_WINDOW_CALLS
    quarantined_until: float = 0.0
    sticky_sessions:   set[str] = field(default_factory=set)

# --- Internal request envelope ---

@dataclass(frozen=True)
class RouteRequest:
    """An inbound call after signature/membership check.
       Constructed by the transport layer before being handed to the bus."""
    capability:    CapabilityName
    version_req:   Version             # the *requested* major+minimum minor
    body:          dict                # the JSON body (params + input)
    caller:        str                 # full NodeID
    trace_id:      str
    session_id:    str | None          # for sticky routing
    deadline_ms:   int                 # absolute monotonic ms
    stream:        bool                # caller-requested
```

### 3.2 `registry.py`

```python
# hearthnet/bus/registry.py
class Registry:
    """Holds CapabilityEntry instances keyed by (node_id, name, version).
       Thread-safe via asyncio.Lock."""

    def __init__(self, our_node_id: str): ...

    # -- local registration --

    def register_local(
        self,
        descriptor: CapabilityDescriptor,
        handler: Callable[[RouteRequest], Awaitable[dict] | AsyncIterator[dict]],
    ) -> None:
        """Register a capability our process offers. Idempotent if descriptor unchanged.
        Raises BusError('schema_invalid') if request/response schemas don't validate against JSON Schema meta-schema.
        Raises BusError('namespace_violation') if name is outside this service's declared prefix."""

    def deregister_local(self, name: CapabilityName, version: Version) -> None: ...

    # -- remote sync (driven by M02 peer events + the periodic manifest fetch) --

    def update_from_peer_manifest(self, peer: PeerRecord, manifest: NodeManifest) -> Diff:
        """Compare offered capabilities to existing entries; add/remove as needed.
           Returns a Diff describing changes."""

    def remove_peer(self, node_id: str) -> int:
        """Remove all entries for a peer. Returns count removed."""

    # -- queries --

    def find(
        self,
        name: CapabilityName,
        version_req: Version,
        params_filter: Callable[[dict], bool] | None = None,
    ) -> list[CapabilityEntry]:
        """Return all entries matching name and version compatibility.
        See CONTRACT §2.1 for compatibility rules."""

    def entry(self, node_id: str, name: CapabilityName, version: Version) -> CapabilityEntry | None: ...

    def all_local(self) -> list[CapabilityEntry]: ...
    def all(self) -> list[CapabilityEntry]: ...

    # -- subscriptions --

    def subscribe(self) -> AsyncIterator[RegistryEvent]:
        """Yield 'added' / 'removed' / 'updated' events. Used by UI topology viz."""

@dataclass(frozen=True)
class Diff:
    added:   list[CapabilityEntry]
    removed: list[CapabilityEntry]
    updated: list[CapabilityEntry]

@dataclass(frozen=True)
class RegistryEvent:
    kind:    str                # "added" | "removed" | "updated"
    entry:   CapabilityEntry
```

### 3.3 `health.py`

```python
# hearthnet/bus/health.py
class HealthTracker:
    """Rolling-window health stats per (node_id, capability_name, version).
       Constant memory: O(nodes × capabilities)."""

    def __init__(self, window: int = HEALTH_WINDOW_CALLS): ...

    def record(self, entry: CapabilityEntry, *, success: bool, latency_ms: float) -> None:
        """Append a sample; recompute p50/p99/success_rate; update entry in place.
        Quarantines entry if success_rate drops below HEALTH_QUARANTINE_THRESHOLD."""

    def is_quarantined(self, entry: CapabilityEntry) -> bool: ...

    def reset(self, entry: CapabilityEntry) -> None:
        """Clear stats — used after quarantine timeout."""
```

Internal: each entry holds a fixed-size ring buffer of `(success, latency_ms)` samples. Old samples drop off as new ones arrive.

### 3.4 `schema.py`

```python
# hearthnet/bus/schema.py
class SchemaValidator:
    """JSON Schema validation, with caching."""

    def __init__(self): ...

    def validate_request(self, descriptor: CapabilityDescriptor, body: dict) -> None:
        """Raises BusError('schema_mismatch') with expected schema_hash if invalid."""

    def validate_response(self, descriptor: CapabilityDescriptor, body: dict) -> None: ...
    def validate_stream_frame(self, descriptor: CapabilityDescriptor, frame: dict) -> None: ...

def compute_schema_hash(descriptor_partial: dict) -> str:
    """BLAKE3 over canonical-JSON. See CONTRACT §11.
       Argument shape:
         {
           'name': ..., 'version': ...,
           'request_schema': {...},
           'response_schema': {...} or None,
           'stream_schema':   {...} or None,
         }
       Returns 'blake3:<hex>'."""
```

### 3.5 `router.py`

```python
# hearthnet/bus/router.py
class Router:
    """Selects the best CapabilityEntry for a request."""

    def __init__(self, registry: Registry, config: BusConfig, our_node_id: str): ...

    def route(self, req: RouteRequest) -> CapabilityEntry | None:
        """Return the chosen entry, or None if no candidate is viable.
        Candidates must:
          - match name and version (CONTRACT §2.1)
          - pass params_compatible() (capability-specific, see §5.5)
          - not be quarantined
          - have in_flight < max_concurrent
          - have last_seen within freshness window (60s)
        Scoring: see §5.4."""

    def route_sticky(self, req: RouteRequest) -> CapabilityEntry | None:
        """If req.session_id is bound to an entry, return that entry if still viable.
        Otherwise fall back to route() and bind."""

    def release_session(self, session_id: str) -> None: ...
```

### 3.6 `trace.py`

```python
# hearthnet/bus/trace.py
@dataclass(frozen=True)
class CallTraceEvent:
    ts:          str
    trace_id:    str
    capability:  CapabilityName
    version:     str
    from_node:   str
    to_node:     str
    is_local:    bool
    result:      str            # "ok" | error_code
    ms:          float
    tokens_in:   int | None     # llm.*-specific
    tokens_out:  int | None
    bytes_in:    int
    bytes_out:   int

class TraceHook:
    """Emits trace events to the ring buffer (X03) and Prometheus metrics."""

    def __init__(self): ...

    def on_call_start(self, req: RouteRequest, entry: CapabilityEntry) -> None: ...
    def on_call_end(
        self,
        req: RouteRequest,
        entry: CapabilityEntry,
        *,
        result: str,
        latency_ms: float,
        bytes_in: int,
        bytes_out: int,
        tokens_in: int | None = None,
        tokens_out: int | None = None,
    ) -> None: ...
```

### 3.7 `CapabilityBus` (the facade)

```python
# hearthnet/bus/__init__.py
class CapabilityBus:
    """The integration point. Services register with this; transport dispatches to it."""

    def __init__(
        self,
        node_id_full: str,
        community_id: str,
        config: BusConfig,
        transport_client: HttpClient,
        community_manifest_provider: Callable[[], CommunityManifest],
    ):
        self.registry  = Registry(our_node_id=node_id_full)
        self.health    = HealthTracker()
        self.schema    = SchemaValidator()
        self.router    = Router(self.registry, config, our_node_id=node_id_full)
        self.trace     = TraceHook()
        self._client   = transport_client
        ...

    # --- service-side: registration ---

    def register_service(self, service: 'Service') -> None:
        """Calls service.capabilities() and registers each with the local handler."""

    def register_capability(
        self,
        descriptor: CapabilityDescriptor,
        handler: Callable[[RouteRequest], Awaitable[dict] | AsyncIterator[dict]],
    ) -> None:
        """Lower-level alternative when a module has no Service class."""

    # --- transport-side: dispatch ---

    async def handle_call(self, req: RouteRequest) -> dict | AsyncIterator[dict]:
        """Called by the X01 server after auth.
        Decides local vs remote, validates schema, runs the handler or makes a remote call,
        records trace + health, returns the payload (or yields frames)."""

    # --- caller-side: outbound capability invocation ---

    async def call(
        self,
        capability: CapabilityName,
        version_req: Version,
        body: dict,
        *,
        session_id: str | None = None,
        timeout_seconds: float | None = None,
    ) -> dict:
        """Used by services that need to invoke other capabilities (e.g. rag.query calling embed.text).
        Goes through the router. If chosen entry is local, runs handler directly.
        If remote, uses X01 client. Records trace + health."""

    async def stream(
        self,
        capability: CapabilityName,
        version_req: Version,
        body: dict,
        *,
        session_id: str | None = None,
    ) -> AsyncIterator[Frame]:
        """Streaming version of call()."""

    # --- peer integration ---

    def on_peer_added(self, peer: PeerRecord) -> None: ...
    def on_peer_updated(self, peer: PeerRecord) -> None: ...
    def on_peer_removed(self, node_id: str) -> None: ...

    # --- introspection (used by UI / CLI) ---

    def topology_snapshot(self) -> 'TopologySnapshot': ...
    def recent_traces(self, n: int = 50) -> list[CallTraceEvent]: ...
    def stats(self) -> dict: ...


@dataclass(frozen=True)
class TopologySnapshot:
    our_node_id:        str
    peers:              list[PeerRecord]
    capabilities_local: list[CapabilityEntry]
    capabilities_remote: list[CapabilityEntry]
    in_flight_total:    int

class BusError(Exception):
    """code in {schema_invalid, namespace_violation, schema_mismatch, not_found, capacity_exceeded,
               quarantined, partition, timeout, internal_error}"""
    code: str
```

---

## 4. The Service protocol (consumed from `services/base.py`)

```python
# hearthnet/services/base.py
class Service(Protocol):
    """Implemented by every L4 service module."""
    name:    str            # "llm" | "rag" | "marketplace" | ...
    version: str            # service version, separate from capability version

    def capabilities(self) -> list[tuple[CapabilityDescriptor, Callable]]:
        """Return (descriptor, handler) pairs for each capability this service offers.
        Handlers signature: (RouteRequest) -> Awaitable[dict] | AsyncIterator[dict]"""

    async def start(self) -> None:
        """Warm up backends, open DBs, etc."""

    async def stop(self) -> None:
        """Release resources."""

    def health(self) -> dict:
        """Implementation-specific health blob (used by /health)."""
```

---

## 5. Behaviour

### 5.1 Bootstrap

```
node.py creates CapabilityBus
  ↓
node.py instantiates services, calls bus.register_service(s) for each
  ↓
each service.start() runs (model loaded, DB opened, etc.)
  ↓
node.py wires bus.on_peer_added <- PeerRegistry.subscribe()
  ↓
node.py wires X01 server handler to bus.handle_call
  ↓
bus is live
```

### 5.2 Peer event handling

When [M02](M02-discovery.md) emits `PeerEvent("added")` with a verified manifest:

```
bus.on_peer_added(peer)
  → registry.update_from_peer_manifest(peer, peer.manifest) → Diff
  → for each added entry: emit RegistryEvent('added')
  → for each removed entry: emit RegistryEvent('removed')
```

### 5.3 Inbound call lifecycle (`handle_call`)

```
1. transport receives, verifies signature, builds RouteRequest
2. bus.handle_call(req):
   a. session_id present?
        yes → entry = router.route_sticky(req)
        no  → entry = router.route(req)
   b. entry is None → raise BusError('not_found')
   c. enforce trust_required (compare against caller's level in community manifest)
   d. validate_request(entry.descriptor, req.body)
   e. entry.in_flight >= max_concurrent → raise BusError('capacity_exceeded') with retry_after
   f. entry.in_flight += 1
   g. trace.on_call_start(req, entry)
   h. if entry.is_local:
        result = await entry.handler(req)
      else:
        result = await self._client.call(entry.endpoint, ...)
   i. validate_response(entry.descriptor, result)  (if non-stream)
   j. trace.on_call_end(...), health.record(...)
   k. entry.in_flight -= 1
   l. return result
```

For streaming: same flow but `result` is an async iterator; validation is per-frame; final telemetry recorded on `done` or `error`.

### 5.4 Routing algorithm (Router.route)

```python
def route(req):
    candidates = registry.find(req.capability, req.version_req)
    candidates = [
        e for e in candidates
        if not health.is_quarantined(e)
        and e.in_flight < e.descriptor.max_concurrent
        and (e.is_local or e.last_seen > monotonic() - 60)
        and params_compatible(e.descriptor.params, req.body.get("params", {}))
    ]
    if not candidates:
        return None
    if config.prefer_local:
        local = [e for e in candidates if e.is_local]
        if local and local[0].in_flight / max(local[0].descriptor.max_concurrent, 1) < config.local_load_threshold:
            return local[0]
    return min(candidates, key=score)

def score(e):
    latency = e.p50_latency_ms if e.p50_latency_ms > 0 else 500.0   # unknown → assume 500ms
    load = e.in_flight / max(e.descriptor.max_concurrent, 1)
    reliability_penalty = (1 - e.success_rate) * 1000
    locality_bonus = -50 if e.is_local else 0
    return latency * (1 + load) + reliability_penalty + locality_bonus
```

### 5.5 `params_compatible` (per-capability)

The bus alone cannot know which `params` matter for compatibility (model name for `llm.chat`, corpus for `rag.query`). Services register a `params_compatible` predicate alongside their descriptor:

```python
# In service's capabilities() return value, tuple is actually:
#   (descriptor, handler, params_compatible)
# where params_compatible: Callable[[dict, dict], bool]
#   args: (offered_params, requested_params) → True if requested can be served
```

Default predicate: `lambda offered, requested: True` (any-matches-any). LLM service overrides to check model/quant/ctx; RAG overrides to check corpus name; etc. Documented per-service in M04 / M05 / etc.

### 5.6 Sticky routing

For multi-turn capabilities (`llm.chat` continuations, future `chat.thread`):

- Caller passes `session_id`
- First call: router picks an entry, records `entry.sticky_sessions.add(session_id)`
- Subsequent calls with same `session_id`: router returns same entry if still viable
- TTL: 10 minutes idle (driven by a background sweeper)
- On entry removal (peer left): session unbinds; next call gets a new entry; caller MAY observe context loss (capability handler returns `bad_request` if context required)

### 5.7 Quarantine

```
health.record(entry, success, latency):
    append to ring buffer
    recompute success_rate over last HEALTH_WINDOW_CALLS samples (or fewer if young)
    if success_rate < HEALTH_QUARANTINE_THRESHOLD:
        entry.quarantined_until = monotonic() + HEALTH_QUARANTINE_SECONDS
        log.warning("quarantined", capability, node_id, success_rate)
        metrics.counter("hearthnet_quarantines_total").inc()

router.route considers quarantined_until <= monotonic() before including.
```

After quarantine timeout, the next call is a "probe": if it succeeds, history resets; if it fails, immediate re-quarantine.

### 5.8 Outbound `call` from a service

```
service code: await bus.call("embed.text", (1,0), {"params": {...}, "input": {...}})
  → router.route(...) → entry
  → if entry.is_local: dispatch to handler directly (no HTTP roundtrip)
  → else: client.call(entry.endpoint, ...)
```

Local short-circuit is the reason a service in the same process can use the bus without paying network cost.

---

## 6. Errors (BusError code mapping)

| BusError code | Wire `ErrorCode` | HTTP status |
|---------------|-----------------|-------------|
| `schema_invalid` | (raised at registration; never on wire) | — |
| `namespace_violation` | (raised at registration) | — |
| `schema_mismatch` | `schema_mismatch` | 400 |
| `not_found` | `not_found` | 404 |
| `capacity_exceeded` | `capacity_exceeded` | 429 |
| `quarantined` | `partition` | 503 |
| `partition` | `partition` | 503 |
| `timeout` | `timeout` | 408 |
| `internal_error` | `internal_error` | 500 |

Plus auth-level errors raised before the bus sees the request: `unauthorized`, `revoked`, `invalid_signature`, `expired`, `rate_limited` — see [X01 §3.3](../cross-cutting/X01-transport.md).

---

## 7. Configuration

From [X04](../cross-cutting/X04-config.md):

```python
config.bus.prefer_local
config.bus.local_load_threshold
```

Constants used: `HEALTH_WINDOW_CALLS`, `HEALTH_QUARANTINE_THRESHOLD`, `HEALTH_QUARANTINE_SECONDS`.

---

## 8. Tests

### Unit

- `test_register_local_validates_descriptor`
- `test_register_local_namespace_violation_raises`
- `test_schema_hash_stable_across_runs`
- `test_schema_hash_changes_on_schema_change`
- `test_router_prefers_local_when_underloaded`
- `test_router_prefers_remote_when_local_overloaded`
- `test_router_skips_quarantined`
- `test_router_breaks_ties_by_latency_then_reliability`
- `test_health_quarantines_at_threshold`
- `test_health_resets_after_quarantine_window`
- `test_params_compatible_predicate_invoked`
- `test_sticky_session_binds_then_unbinds_on_peer_removal`
- `test_in_flight_decrements_on_handler_exception`

### Integration

- `test_two_nodes_route_to_each_other` — two in-process buses, one registers `llm.chat`, the other calls
- `test_three_nodes_load_balance` — three providers, 100 calls, distribution within 30% of even
- `test_quarantine_after_chaos` — fault inject one provider, observe quarantine then recovery
- `test_streaming_call_records_full_trace`
- `test_sticky_routing_preserves_session_across_calls`

---

## 9. Cross-references

| What | Where |
|------|-------|
| Capability descriptor concept | [CONTRACT §2, §11](../CAPABILITY_CONTRACT.md) |
| Schema hash computation | [CONTRACT §11](../CAPABILITY_CONTRACT.md) |
| Version compatibility | [CONTRACT §2.1](../CAPABILITY_CONTRACT.md) |
| Wire-level error codes | [CONTRACT §9](../CAPABILITY_CONTRACT.md) |
| Transport dispatch | [X01 §3.3](../cross-cutting/X01-transport.md) |
| Peer registry | [M02 §3.1](M02-discovery.md) |
| Trace ring buffer | [X03 §5](../cross-cutting/X03-observability.md) |
| Service protocol consumers | [M04](M04-llm.md), [M05](M05-rag.md), [M06](M06-marketplace.md), [M07](M07-file-blobs.md), [M10](M10-chat.md), [M11](M11-embedding.md) |
| UI consumes topology_snapshot | [M08 §3.2](M08-ui.md) |

---

## 10. Open questions

1. **Per-capability params predicate registration** — currently a third tuple element. Cleaner alternative: store as method on a `CapabilitySpec` subclass. Decide before M04 lands.
2. **Sticky session TTL** — fixed 10 minutes? Or per-capability declared? MVP: fixed. Phase 2: declared.
3. **Load balancing fairness** — current scorer is greedy. Should we add a small random jitter to avoid herd-on-fastest? MVP: no. If we see herd in tests, add ε-noise.
4. **Schema cache invalidation** — currently keyed by `schema_hash`. Implicit invalidation on hash change. Should be sufficient.
