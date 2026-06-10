"""Bus trace events for call tracking."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CallTraceEvent:
    ts: str  # ISO timestamp
    trace_id: str
    capability: str
    version: str
    caller: str
    routed_to: str  # node_id
    is_local: bool
    success: bool
    error_code: str | None
    latency_ms: int
    bytes_in: int
    bytes_out: int


class TraceHook:
    """Emits trace events to the ring buffer (X03) and Prometheus metrics."""

    def __init__(self, ring_buffer: Any = None, metrics: Any = None) -> None:
        self._ring = ring_buffer
        self._metrics = metrics

    def record(self, event: CallTraceEvent) -> None:
        if self._ring is not None:
            try:
                self._ring.push(event)
            except Exception:
                pass
