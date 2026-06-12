from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any

from hearthnet.bus.capability import (
    CapabilityDescriptor,
    CapabilityEntry,
    Handler,
    ParamsPredicate,
    RouteRequest,
)
from hearthnet.bus.health import HealthTracker
from hearthnet.bus.registry import Diff, Registry, RegistryEvent
from hearthnet.bus.router import BusConfig, Router
from hearthnet.types import CapabilityName, HearthNetError, Version


class BusError(HearthNetError):
    pass


class InMemoryTransport:
    def __init__(self) -> None:
        self._buses: dict[str, CapabilityBus] = {}

    def register(self, bus: CapabilityBus) -> None:
        self._buses[bus.node_id_full] = bus

    async def call(self, node_id: str, req: RouteRequest) -> dict[str, Any]:
        try:
            bus = self._buses[node_id]
        except KeyError as exc:
            raise BusError("partition", f"node {node_id} is not reachable") from exc
        inbound = RouteRequest(
            capability=req.capability,
            version_req=req.version_req,
            body=req.body,
            caller=req.caller,
            trace_id=req.trace_id,
            session_id=req.session_id,
            deadline_ms=req.deadline_ms,
            stream=req.stream,
        )
        return await bus.handle_call(inbound, local_only=True)


@dataclass(frozen=True)
class CallTraceEvent:
    trace_id: str
    capability: CapabilityName
    from_node: str
    to_node: str
    result: str
    ms: float


@dataclass(frozen=True)
class TopologySnapshot:
    our_node_id: str
    peers: list[dict[str, Any]]
    capabilities_local: list[dict[str, Any]]
    capabilities_remote: list[dict[str, Any]]
    in_flight_total: int
    traces: list[CallTraceEvent]


class CapabilityBus:
    def __init__(
        self,
        node_id_full: str,
        community_id: str,
        transport: InMemoryTransport | None = None,
        config: BusConfig | None = None,
    ) -> None:
        self.node_id_full = node_id_full
        self.community_id = community_id
        self.registry = Registry(our_node_id=node_id_full)
        self.health = HealthTracker()
        self.router = Router(self.registry, config)
        self.transport = transport or InMemoryTransport()
        self.transport.register(self)
        self._traces: list[CallTraceEvent] = []
        self._offline_stash: list[tuple[CapabilityDescriptor, Handler, ParamsPredicate | None]] = []

    def register_capability(
        self,
        descriptor: CapabilityDescriptor,
        handler: Handler,
        params_compatible: ParamsPredicate | None = None,
    ) -> None:
        self.registry.register_local(descriptor, handler, params_compatible)

    def register_service(self, service: Any) -> None:
        for item in service.capabilities():
            descriptor, handler, *rest = item
            predicate = rest[0] if rest else None
            self.register_capability(descriptor, handler, predicate)

    async def call(
        self,
        capability: CapabilityName,
        version_req: Version,
        body: dict[str, Any],
        *,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        req = RouteRequest(
            capability=capability,
            version_req=version_req,
            body=body,
            caller=self.node_id_full,
            trace_id=uuid.uuid4().hex,
            session_id=session_id,
            deadline_ms=int((time.monotonic() + 10) * 1000),
        )
        return await self.handle_call(req)

    async def handle_call(self, req: RouteRequest, *, local_only: bool = False) -> dict[str, Any]:
        entry = self.router.route_sticky(req) if req.session_id else self.router.route(req)
        if entry is None:
            raise BusError("not_found", f"no provider for {req.capability}@{req.version_req}")
        started = time.monotonic()
        entry.in_flight += 1
        try:
            if entry.is_local:
                if entry.handler is None:
                    raise BusError("not_implemented", entry.descriptor.name)
                result = await entry.handler(req)
            elif local_only:
                raise BusError("not_found", f"remote entry cannot satisfy inbound {req.capability}")
            else:
                result = await self.transport.call(entry.node_id, req)
            elapsed = (time.monotonic() - started) * 1000
            self.health.record(entry, success=True, latency_ms=elapsed)
            self._traces.append(
                CallTraceEvent(
                    req.trace_id, req.capability, req.caller, entry.node_id, "ok", elapsed
                )
            )
            return result
        except HearthNetError as exc:
            elapsed = (time.monotonic() - started) * 1000
            self.health.record(entry, success=False, latency_ms=elapsed)
            self._traces.append(
                CallTraceEvent(
                    req.trace_id, req.capability, req.caller, entry.node_id, exc.code, elapsed
                )
            )
            raise
        finally:
            entry.in_flight -= 1

    async def call_all(
        self,
        capability: CapabilityName,
        version_req: Version,
        body: dict[str, Any],
        *,
        timeout_seconds: float = 5.0,
        include_local: bool = True,
        max_providers: int = 8,
    ) -> list[tuple[str, dict[str, Any]]]:
        """Scatter-gather: call ALL matching providers in parallel.

        Unlike :meth:`call` (routes to a single best provider), this fans the
        request out to every node offering a compatible capability and gathers
        their responses. Used for federated RAG: ask every peer holding the
        corpus, then merge + rerank results.

        Returns a list of ``(node_id, result)`` tuples. Providers that error or
        time out are omitted (failure recorded in health stats).
        """
        import asyncio

        requested_params = dict(body.get("params", {}))
        now = time.monotonic()
        entries = [
            entry
            for entry in self.registry.find(capability, version_req)
            if entry.quarantined_until <= now
            and entry.params_compatible(entry.descriptor.params, requested_params)
        ]
        if not include_local:
            entries = [e for e in entries if not e.is_local]
        # Cap fan-out to avoid request storms on large meshes.
        entries = entries[:max_providers]
        if not entries:
            return []

        async def _invoke(entry: CapabilityEntry) -> tuple[str, dict[str, Any]] | None:
            req = RouteRequest(
                capability=capability,
                version_req=version_req,
                body=body,
                caller=self.node_id_full,
                trace_id=uuid.uuid4().hex,
                deadline_ms=int((time.monotonic() + timeout_seconds) * 1000),
            )
            started = time.monotonic()
            entry.in_flight += 1
            try:
                if entry.is_local:
                    if entry.handler is None:
                        return None
                    result = await entry.handler(req)
                else:
                    result = await self.transport.call(entry.node_id, req)
                elapsed = (time.monotonic() - started) * 1000
                self.health.record(entry, success=True, latency_ms=elapsed)
                return (entry.node_id, result)
            except Exception as exc:
                elapsed = (time.monotonic() - started) * 1000
                self.health.record(entry, success=False, latency_ms=elapsed)
                self._traces.append(
                    CallTraceEvent(
                        req.trace_id,
                        capability,
                        req.caller,
                        entry.node_id,
                        getattr(exc, "code", "error"),
                        elapsed,
                    )
                )
                return None
            finally:
                entry.in_flight -= 1

        async def _guarded(entry: CapabilityEntry) -> tuple[str, dict[str, Any]] | None:
            try:
                return await asyncio.wait_for(_invoke(entry), timeout=timeout_seconds)
            except Exception:
                return None

        gathered = await asyncio.gather(*[_guarded(e) for e in entries])
        return [r for r in gathered if r is not None]

    def deregister_internet_capabilities(self) -> int:
        removed = 0
        for entry in list(self.registry.all_local()):
            if entry.descriptor.params.get("requires_internet"):
                removed_entry = self.registry.deregister_local(
                    entry.descriptor.name, entry.descriptor.version
                )
                if removed_entry and removed_entry.handler:
                    self._offline_stash.append(
                        (
                            removed_entry.descriptor,
                            removed_entry.handler,
                            removed_entry.params_compatible,
                        )
                    )
                    removed += 1
        return removed

    def restore_internet_capabilities(self) -> int:
        restored = 0
        while self._offline_stash:
            descriptor, handler, predicate = self._offline_stash.pop(0)
            self.register_capability(descriptor, handler, predicate)
            restored += 1
        return restored

    def topology_snapshot(self, peers: list[dict[str, Any]] | None = None) -> TopologySnapshot:
        return TopologySnapshot(
            our_node_id=self.node_id_full,
            peers=peers or [],
            capabilities_local=[_entry_view(entry) for entry in self.registry.all_local()],
            capabilities_remote=[_entry_view(entry) for entry in self.registry.all_remote()],
            in_flight_total=sum(entry.in_flight for entry in self.registry.all()),
            traces=list(self._traces[-50:]),
        )


def _entry_view(entry: CapabilityEntry) -> dict[str, Any]:
    return {
        "node_id": entry.node_id,
        "name": entry.descriptor.name,
        "version": entry.descriptor.version_str,
        "local": entry.is_local,
        "params": dict(entry.descriptor.params),
        "success_rate": entry.success_rate,
        "quarantined": entry.quarantined_until > time.monotonic(),
    }
