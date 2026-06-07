# M09 — Emergency Mode Detector

**Spec version:** v1.0
**Depends on:** M03 (bus, to deregister internet-dependent capabilities), X04 (config), X03 (observability), `httpx`, `socket`
**Depended on by:** M08 (UI shows banner), M04 (re-registers internet backends on restore), M02 (increases discovery cadence)

---

## 1. Responsibility

Detect whether the node has working internet access. Publish state transitions locally. Cause the bus to deregister/re-register internet-dependent capabilities and let other modules react.

Out of scope:
- VPN / overlay status
- Per-service connectivity checks
- Cellular signal strength

---

## 2. File layout

```
hearthnet/emergency/
├── __init__.py
├── detector.py        # Detector: probe loop, state machine
└── state.py           # EmergencyState dataclass + StateBus
```

---

## 3. Public API

### 3.1 `state.py`

```python
# hearthnet/emergency/state.py
from dataclasses import dataclass
from typing import Literal

Mode = Literal["online", "degraded", "offline"]

@dataclass(frozen=True)
class EmergencyState:
    mode:        Mode
    since:       str           # RFC 3339
    last_probe:  str
    probe_results: dict[str, bool]   # target → success

class StateBus:
    """In-process pubsub for state changes. UI and other modules subscribe."""

    def __init__(self): ...
    def current(self) -> EmergencyState: ...
    async def subscribe(self) -> AsyncIterator[EmergencyState]: ...
    def _emit(self, state: EmergencyState) -> None: ...    # internal
```

### 3.2 `detector.py`

```python
# hearthnet/emergency/detector.py
class Detector:
    def __init__(
        self,
        config: EmergencyConfig,
        bus: CapabilityBus,
        state_bus: StateBus,
    ):
        ...

    async def run(self) -> None:
        """Main loop. Cancel-safe.
        Probe cadence:
          - online → every EMERGENCY_PROBE_INTERVAL_ONLINE (10s)
          - degraded → every EMERGENCY_PROBE_INTERVAL_OFFLINE (2s)
          - offline → every EMERGENCY_PROBE_INTERVAL_OFFLINE (2s)
        Each tick:
          1. probe all targets concurrently with 2s timeout
          2. compute new mode
          3. apply debounce (EMERGENCY_TRANSITION_DEBOUNCE_SECONDS, anti-flap)
          4. if mode changed:
              - state_bus._emit(new_state)
              - if entered offline: bus deregisters internet-dependent capabilities
              - if entered online: bus re-registers them
              - emit log + metric
        """

    async def shutdown(self) -> None: ...

    # --- probe primitives ---

    async def _probe_dns(self, host: str) -> bool: ...
    async def _probe_http(self, url: str) -> bool: ...
```

---

## 4. State machine

```
              ┌────────┐  any probe fails  ┌──────────┐
              │ ONLINE ├──────────────────►│ DEGRADED │
              └───┬────┘                    └─────┬────┘
                  ▲                               │  ≥2 probes fail for 30s
                  │ all probes pass for 10s       ▼
                  │                          ┌──────────┐
                  └──────────────────────────┤ OFFLINE  │
                                             └──────────┘
```

Anti-flap: if more than 3 transitions occur within 60 seconds, the detector stays in the more pessimistic state (degraded or offline) until the window passes.

---

## 5. Behaviour

### 5.1 Probes

Default targets (from `EmergencyConfig.probe_targets`):

- `1.1.1.1` (DNS A query)
- `8.8.8.8` (DNS A query)
- `cloudflare.com` (HTTPS HEAD)
- `quad9.net` (HTTPS HEAD)

Mode rule:

- `online` requires all 4 succeed
- `offline` requires ≥ 2 to fail
- everything between is `degraded`

### 5.2 Effects on the bus

When entering `offline`:

```python
for entry in bus.registry.all_local():
    if entry.descriptor.params.get("requires_internet"):
        bus.registry.deregister_local(entry.descriptor.name, entry.descriptor.version)
        log.info("offline.deregistered", capability=entry.descriptor.name)
```

When returning to `online`:

```python
for backend in llm_service._backends:
    if backend.requires_internet:
        llm_service._register_backend(backend)        # re-emit descriptors
```

`requires_internet` is a convention: services that wrap remote APIs (`anthropic_api`, `hf_api`) set this flag on their `BackendModel` and inject it into the capability descriptor params at registration time.

### 5.3 Effects on M02 discovery

Detector also calls `peer_registry.set_pruning_aggressive(offline)`:

- Offline: prune stale peers after 30 s instead of 90
- Online: standard 90 s

This makes offline mode adapt faster to neighbour churn.

### 5.4 UI surface (M08 consumes)

The state bus is the source for the amber `INTERNET OFFLINE — LOKAL AKTIV` banner. UI subscribes; flips theme; switches LLM passthrough to local-only backends visibly.

### 5.5 Clock sanity probe (only when online)

When online for ≥ 30 s, send an extra HEAD to a single anchor and check the `Date` header. If our system clock differs by > 60 s, log a warning. We do NOT auto-correct.

### 5.6 No on-wire pubsub

`emergency.mode.changed` is local only ([CONTRACT §8](../CAPABILITY_CONTRACT.md)). Other nodes do their own detection.

---

## 6. Errors

This module raises nothing externally; all failures are logged. Internal probe failures are the *normal* signal that drives state.

---

## 7. Configuration

From [X04 §3](../cross-cutting/X04-config.md):

```python
config.emergency.probe_targets    # list[str]
```

Constants: `EMERGENCY_PROBE_INTERVAL_ONLINE`, `EMERGENCY_PROBE_INTERVAL_OFFLINE`, `EMERGENCY_PROBE_TIMEOUT_SECONDS`, `EMERGENCY_TRANSITION_DEBOUNCE_SECONDS`.

---

## 8. Tests

### Unit
- `test_state_transitions_with_synthetic_probes`
- `test_anti_flap_holds_pessimistic_state`
- `test_deregister_called_on_offline_entry`
- `test_reregister_called_on_online_entry`

### Integration
- `test_demo_unplug_triggers_banner_within_5s` — simulate WAN drop with `iptables` rule, observe state change

---

## 9. Cross-references

| What | Where |
|------|-------|
| Online/offline pubsub topic (local) | [CONTRACT §8](../CAPABILITY_CONTRACT.md) |
| LLM internet-dependent backends | [M04 §4.3](M04-llm.md) |
| Discovery cadence change | [M02 §4.3](M02-discovery.md) |
| UI banner | [M08 §5.5](M08-ui.md) |

---

## 10. Open questions

1. **Captive portal detection** — Phase 2: probe a known-content URL and compare body hash. MVP: false positives accepted.
2. **IPv6-only networks** — current probes are dual-stack via OS. Should work; not yet tested.
3. **Custom probe scripts** — Phase 2: let users add their own targets.
