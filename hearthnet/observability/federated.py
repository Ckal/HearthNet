"""Federated metrics aggregation (X07)."""
from __future__ import annotations

import asyncio
import logging
import math
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ── Dataclasses ───────────────────────────────────────────────────────────────


@dataclass
class NodeMetricsTick:
    """Single per-node metrics sample."""

    node_id: str
    community_id: str
    tick_at: float

    active_capabilities: int = 0
    events_per_min: float = 0.0
    peers_online: int = 0

    llm_requests_total: int = 0
    rag_requests_total: int = 0

    gpu_memory_mb: float | None = None
    cpu_percent: float = 0.0
    memory_mb: float = 0.0

    online_seconds: int = 0


@dataclass
class CommunityMetrics:
    """Aggregated metrics across all members of a community (full detail)."""

    community_id: str
    member_count: int
    online_count: int

    events_per_min_total: float
    capabilities_total: int

    ticks: list[NodeMetricsTick]  # per-node detail
    sampled_at: float


@dataclass
class AggregatedSnapshot:
    """
    Anonymised/banded aggregate for federated peers (less information
    at greater distance per X07 design rule).
    """

    community_id: str
    member_count_band: str   # e.g. "10-20"
    online_count_band: str
    events_per_min_band: str
    capabilities_count: int
    federation_links_count: int
    sampled_at: float


# ── Helpers ───────────────────────────────────────────────────────────────────


def _band(value: float, steps: list[int]) -> str:
    """Return a band string like '10-20' for *value* given boundary *steps*."""
    for i, upper in enumerate(steps):
        lower = steps[i - 1] if i > 0 else 0
        if value < upper:
            return f"{lower}-{upper}"
    last = steps[-1] if steps else 0
    return f"{last}+"


_MEMBER_BANDS = [5, 10, 20, 50, 100, 250, 500, 1000]
_ONLINE_BANDS = [2, 5, 10, 25, 50, 100, 250, 500]
_EPM_BANDS = [10, 50, 100, 500, 1000, 5000, 10000]


def _collect_system_metrics() -> dict[str, float]:
    """Snapshot CPU / memory using psutil if available; otherwise zeros."""
    try:
        import psutil  # type: ignore[import]
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory().used / (1024 * 1024)
        return {"cpu_percent": cpu, "memory_mb": mem}
    except ImportError:
        return {"cpu_percent": 0.0, "memory_mb": 0.0}
    except Exception:
        return {"cpu_percent": 0.0, "memory_mb": 0.0}


def _collect_gpu_memory() -> float | None:
    """Return GPU memory usage in MB if pynvml is available."""
    try:
        import pynvml  # type: ignore[import]
        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        info = pynvml.nvmlDeviceGetMemoryInfo(handle)
        return info.used / (1024 * 1024)
    except Exception:
        return None


# ── FederatedMetricsExporter ──────────────────────────────────────────────────


class FederatedMetricsExporter:
    """
    Snapshots local metrics and publishes them to the community bus topic
    and optionally to an OTLP collector.
    """

    def __init__(
        self,
        node_id: str = "",
        community_id: str = "",
        bus: Any = None,
    ) -> None:
        self._node_id = node_id
        self._community_id = community_id
        self._bus = bus
        self._start_time: float = time.time()

    def collect_tick(self, bus: Any = None) -> NodeMetricsTick:
        """Snapshot current metrics into a :class:`NodeMetricsTick`."""
        _bus = bus or self._bus
        sys_metrics = _collect_system_metrics()

        # Collect capability count from bus
        active_caps = 0
        if _bus is not None:
            try:
                caps = _bus.list_capabilities()
                active_caps = len(caps) if caps else 0
            except Exception:
                pass

        # Collect request counters from prometheus registry if available
        llm_total = 0
        rag_total = 0
        try:
            from hearthnet.observability.metrics import _STD  # noqa: PLC0415
            llm_counter = _STD.get("hearthnet_llm_requests_total")
            rag_counter = _STD.get("hearthnet_rag_requests_total")
            if llm_counter is not None and hasattr(llm_counter, "_value"):
                llm_total = int(llm_counter._value.get() or 0)
            if rag_counter is not None and hasattr(rag_counter, "_value"):
                rag_total = int(rag_counter._value.get() or 0)
        except Exception:
            pass

        online_secs = int(time.time() - self._start_time)

        return NodeMetricsTick(
            node_id=self._node_id,
            community_id=self._community_id,
            tick_at=time.time(),
            active_capabilities=active_caps,
            events_per_min=0.0,  # filled by aggregator from event log
            peers_online=0,      # filled by aggregator from peer registry
            llm_requests_total=llm_total,
            rag_requests_total=rag_total,
            gpu_memory_mb=_collect_gpu_memory(),
            cpu_percent=sys_metrics["cpu_percent"],
            memory_mb=sys_metrics["memory_mb"],
            online_seconds=online_secs,
        )

    async def push_to_community(self, tick: NodeMetricsTick, bus: Any = None) -> None:
        """Publish *tick* to the bus topic ``observability.metrics.tick.<node_id>``."""
        _bus = bus or self._bus
        if _bus is None:
            logger.debug("FederatedMetricsExporter.push_to_community: no bus configured")
            return
        topic = f"observability.metrics.tick.{tick.node_id}"
        payload: dict[str, Any] = {
            "node_id": tick.node_id,
            "community_id": tick.community_id,
            "tick_at": tick.tick_at,
            "active_capabilities": tick.active_capabilities,
            "events_per_min": tick.events_per_min,
            "peers_online": tick.peers_online,
            "llm_requests_total": tick.llm_requests_total,
            "rag_requests_total": tick.rag_requests_total,
            "gpu_memory_mb": tick.gpu_memory_mb,
            "cpu_percent": tick.cpu_percent,
            "memory_mb": tick.memory_mb,
            "online_seconds": tick.online_seconds,
        }
        try:
            result = _bus.call(
                "bus.publish",
                (1, 0),
                {"topic": topic, "event": "metrics_tick", "data": payload},
            )
            if asyncio.iscoroutine(result):
                await result
        except Exception as exc:
            logger.warning("FederatedMetricsExporter.push_to_community failed: %s", exc)

    async def push_otlp(self, endpoint: str, tick: NodeMetricsTick) -> None:
        """
        Export *tick* via OTLP HTTP. Requires opentelemetry-exporter-otlp-proto-http.

        Delegates to :class:`OtlpExporter`.
        """
        try:
            from hearthnet.observability.otlp_export import OtlpExporter  # noqa: PLC0415
            exporter = OtlpExporter(endpoint)
            await exporter.export_metrics(tick)
        except ImportError:
            logger.debug("push_otlp: opentelemetry not installed — skipping")
        except Exception as exc:
            logger.warning("FederatedMetricsExporter.push_otlp failed: %s", exc)


# ── MetricsAggregator ─────────────────────────────────────────────────────────


class MetricsAggregator:
    """
    Receives NodeMetricsTick events from all community members and builds
    community-level and federated snapshots.
    """

    def __init__(
        self,
        community_id: str,
        max_ticks_per_node: int = 60,
    ) -> None:
        self._community_id = community_id
        self._max_ticks = max_ticks_per_node
        # node_id → deque of ticks (newest last)
        self._ticks: dict[str, deque[NodeMetricsTick]] = defaultdict(
            lambda: deque(maxlen=self._max_ticks)
        )
        self._federation_links: dict[str, int] = {}  # peer_community_id → count

    def apply_tick(self, tick: NodeMetricsTick) -> None:
        """Incorporate a new tick from a community member."""
        self._ticks[tick.node_id].append(tick)

    def community_snapshot(self) -> CommunityMetrics:
        """Return the latest community-wide aggregate."""
        now = time.time()
        latest_ticks: list[NodeMetricsTick] = []
        online_cutoff = now - 120  # consider online if tick within 2 min

        for node_deque in self._ticks.values():
            if node_deque:
                latest_ticks.append(node_deque[-1])

        online = [t for t in latest_ticks if t.tick_at >= online_cutoff]
        total_epm = sum(t.events_per_min for t in online)
        total_caps = sum(t.active_capabilities for t in online)

        return CommunityMetrics(
            community_id=self._community_id,
            member_count=len(self._ticks),
            online_count=len(online),
            events_per_min_total=total_epm,
            capabilities_total=total_caps,
            ticks=list(latest_ticks),
            sampled_at=now,
        )

    def federated_snapshot(self, peer_community_id: str) -> AggregatedSnapshot:
        """
        Return a banded/anonymised snapshot suitable for sharing with a
        federated peer community.
        """
        snap = self.community_snapshot()
        fed_links = len(self._federation_links)

        return AggregatedSnapshot(
            community_id=self._community_id,
            member_count_band=_band(snap.member_count, _MEMBER_BANDS),
            online_count_band=_band(snap.online_count, _ONLINE_BANDS),
            events_per_min_band=_band(snap.events_per_min_total, _EPM_BANDS),
            capabilities_count=snap.capabilities_total,
            federation_links_count=fed_links,
            sampled_at=snap.sampled_at,
        )

    def record_federation_link(self, peer_community_id: str) -> None:
        """Track that we have an active federation link to *peer_community_id*."""
        self._federation_links[peer_community_id] = self._federation_links.get(
            peer_community_id, 0
        ) + 1
