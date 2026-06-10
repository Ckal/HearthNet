from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

Mode = Literal["online", "degraded", "offline"]


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class EmergencyState:
    mode: Mode
    since: str
    last_probe: str
    probe_results: dict[str, bool] = field(default_factory=dict)


class StateBus:
    def __init__(self) -> None:
        now = utc_now()
        self._state = EmergencyState(mode="online", since=now, last_probe=now, probe_results={})

    def current(self) -> EmergencyState:
        return self._state

    def emit_probe(self, probe_results: dict[str, bool]) -> EmergencyState:
        failed = sum(1 for ok in probe_results.values() if not ok)
        if failed == 0:
            mode: Mode = "online"
        elif failed >= 2:
            mode = "offline"
        else:
            mode = "degraded"
        now = utc_now()
        since = now if mode != self._state.mode else self._state.since
        self._state = EmergencyState(
            mode=mode, since=since, last_probe=now, probe_results=dict(probe_results)
        )
        return self._state
