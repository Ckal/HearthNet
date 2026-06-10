from __future__ import annotations

import time
from collections import defaultdict, deque

from hearthnet.bus.capability import CapabilityEntry

HEALTH_WINDOW_CALLS = 5
HEALTH_QUARANTINE_SECONDS = 30
HEALTH_QUARANTINE_THRESHOLD = 0.60


class HealthTracker:
    def __init__(self, window: int = HEALTH_WINDOW_CALLS) -> None:
        self.window = window
        self._samples: dict[tuple[str, str, tuple[int, int]], deque[tuple[bool, float]]] = (
            defaultdict(lambda: deque(maxlen=window))
        )

    def record(self, entry: CapabilityEntry, *, success: bool, latency_ms: float) -> None:
        key = (entry.node_id, entry.descriptor.name, entry.descriptor.version)
        samples = self._samples[key]
        samples.append((success, latency_ms))
        latencies = sorted(sample[1] for sample in samples)
        successes = sum(1 for sample in samples if sample[0])
        entry.success_rate = successes / len(samples)
        entry.p50_latency_ms = latencies[len(latencies) // 2]
        entry.p99_latency_ms = latencies[-1]
        if len(samples) >= self.window and entry.success_rate < HEALTH_QUARANTINE_THRESHOLD:
            entry.quarantined_until = time.monotonic() + HEALTH_QUARANTINE_SECONDS

    def reset(self, entry: CapabilityEntry) -> None:
        key = (entry.node_id, entry.descriptor.name, entry.descriptor.version)
        self._samples.pop(key, None)
        entry.success_rate = 1.0
        entry.quarantined_until = 0.0
