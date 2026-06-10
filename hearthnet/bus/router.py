"""M03 - Capability Bus - Router.

Spec: docs/M03-bus.md §3.5 (routing) §5.4 (scoring algorithm)
Impl-ref: impl_ref.md §7 Router

Scoring: latency-weighted success rate, capacity headroom, prefer local.
Quarantine threshold: HEALTH_QUARANTINE_THRESHOLD (hearthnet/constants.py).
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from hearthnet.bus.capability import CapabilityEntry, RouteRequest
from hearthnet.bus.registry import Registry


@dataclass(frozen=True)
class BusConfig:
    prefer_local: bool = True
    local_load_threshold: float = 0.80
    freshness_seconds: int = 60


class Router:
    def __init__(self, registry: Registry, config: BusConfig | None = None) -> None:
        self.registry = registry
        self.config = config or BusConfig()
        self._sticky: dict[str, CapabilityEntry] = {}

    def route(self, req: RouteRequest) -> CapabilityEntry | None:
        requested_params = dict(req.body.get("params", {}))
        now = time.monotonic()
        candidates = [
            entry
            for entry in self.registry.find(req.capability, req.version_req)
            if entry.quarantined_until <= now
            and entry.in_flight < entry.descriptor.max_concurrent
            and (entry.is_local or entry.last_seen > now - self.config.freshness_seconds)
            and entry.params_compatible(entry.descriptor.params, requested_params)
        ]
        if not candidates:
            return None
        if self.config.prefer_local:
            local = [entry for entry in candidates if entry.is_local]
            if local:
                best_local = min(local, key=_score)
                load = best_local.in_flight / max(best_local.descriptor.max_concurrent, 1)
                if load < self.config.local_load_threshold:
                    return best_local
        return min(candidates, key=_score)

    def route_sticky(self, req: RouteRequest) -> CapabilityEntry | None:
        if req.session_id and req.session_id in self._sticky:
            sticky_entry = self._sticky[req.session_id]
            if sticky_entry in self.registry.find(
                req.capability, req.version_req
            ) and self._is_viable(sticky_entry):
                return sticky_entry
        routed_entry = self.route(req)
        if req.session_id and routed_entry is not None:
            self._sticky[req.session_id] = routed_entry
            routed_entry.sticky_sessions.add(req.session_id)
        return routed_entry

    def release_session(self, session_id: str) -> None:
        released = self._sticky.pop(session_id, None)
        if released is not None:
            released.sticky_sessions.discard(session_id)

    def _is_viable(self, entry: CapabilityEntry) -> bool:
        return (
            entry.quarantined_until <= time.monotonic()
            and entry.in_flight < entry.descriptor.max_concurrent
        )


def _score(entry: CapabilityEntry) -> float:
    latency = entry.p50_latency_ms if entry.p50_latency_ms > 0 else 500.0
    load = entry.in_flight / max(entry.descriptor.max_concurrent, 1)
    reliability_penalty = (1.0 - entry.success_rate) * 1000
    locality_bonus = -50 if entry.is_local else 0
    return latency * (1 + load) + reliability_penalty + locality_bonus

