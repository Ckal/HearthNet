from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal

Mode = Literal["online", "degraded", "offline"]


@dataclass(frozen=True)
class EmergencyState:
    mode: Mode
    changed_at: float  # monotonic timestamp
    probe_results: dict[str, bool]  # target -> success
    consecutive_fails: int = 0

    @property
    def mode_label(self) -> str:
        return {
            "online": "ONLINE",
            "degraded": "DEGRADED — LIMITED",
            "offline": "INTERNET OFFLINE — LOKAL AKTIV",
        }[self.mode]


class StateBus:
    """In-process pub/sub for emergency state changes."""

    def __init__(self) -> None:
        self._state = EmergencyState(mode="online", changed_at=time.monotonic(), probe_results={})
        self._subscribers: list[asyncio.Queue] = []
        self._transition_times: list[float] = []  # for anti-flap

    def current(self) -> EmergencyState:
        return self._state

    async def subscribe(self) -> AsyncIterator[EmergencyState]:
        q: asyncio.Queue = asyncio.Queue(maxsize=10)
        self._subscribers.append(q)
        try:
            while True:
                state = await q.get()
                yield state
        finally:
            self._subscribers.remove(q)

    def emit_probe(self, probe_results: dict[str, bool]) -> EmergencyState:
        """Compute new mode from probe results, apply anti-flap, emit if changed."""
        successes = sum(1 for v in probe_results.values() if v)
        total = len(probe_results)
        fails = total - successes

        if total == 0:
            new_mode: Mode = "online"
        elif fails >= max(2, total // 2):
            new_mode = "offline"
        elif fails > 0:
            new_mode = "degraded"
        else:
            new_mode = "online"

        old_mode = self._state.mode

        # Anti-flap: if too many transitions in last 60s, stay pessimistic
        from hearthnet.constants import (
            EMERGENCY_ANTI_FLAP_MAX_TRANSITIONS,
            EMERGENCY_ANTI_FLAP_WINDOW_SECONDS,
        )

        now = time.monotonic()
        self._transition_times = [
            t for t in self._transition_times if now - t < EMERGENCY_ANTI_FLAP_WINDOW_SECONDS
        ]
        if len(self._transition_times) >= EMERGENCY_ANTI_FLAP_MAX_TRANSITIONS and old_mode in ("degraded", "offline") and new_mode == "online":
            # Too many flaps — hold pessimistic
            new_mode = old_mode  # don't restore yet

        new_state = EmergencyState(
            mode=new_mode,
            changed_at=now if new_mode != old_mode else self._state.changed_at,
            probe_results=probe_results,
            consecutive_fails=self._state.consecutive_fails + (1 if fails > 0 else 0),
        )

        if new_mode != old_mode:
            self._transition_times.append(now)
            self._state = new_state
            self._emit(new_state)
        else:
            self._state = new_state

        return new_state

    def _emit(self, state: EmergencyState) -> None:
        for q in list(self._subscribers):
            with contextlib.suppress(asyncio.QueueFull):
                q.put_nowait(state)
