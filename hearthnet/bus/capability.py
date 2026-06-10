from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from hearthnet.types import CapabilityName, Endpoint, Stability, TrustLevel, Version

Handler = Callable[["RouteRequest"], Awaitable[dict[str, Any]]]
ParamsPredicate = Callable[[dict[str, Any], dict[str, Any]], bool]


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


@dataclass(frozen=True)
class CapabilityDescriptor:
    name: CapabilityName
    version: Version = (1, 0)
    stability: Stability = "stable"
    request_schema: dict[str, Any] = field(default_factory=dict)
    response_schema: dict[str, Any] | None = None
    stream_schema: dict[str, Any] | None = None
    params: dict[str, Any] = field(default_factory=dict)
    max_concurrent: int = 1
    trust_required: TrustLevel | str = "member"
    timeout_seconds: int = 10
    idempotent: bool = True

    @property
    def version_str(self) -> str:
        return f"{self.version[0]}.{self.version[1]}"

    def schema_hash(self) -> str:
        payload = {
            "name": self.name,
            "version": self.version_str,
            "request_schema": self.request_schema,
            "response_schema": self.response_schema,
            "stream_schema": self.stream_schema,
        }
        return "blake3:" + hashlib.sha256(_canonical_json(payload)).hexdigest()


@dataclass
class CapabilityEntry:
    node_id: str
    descriptor: CapabilityDescriptor
    is_local: bool
    handler: Handler | None = None
    endpoint: Endpoint | None = None
    params_compatible: ParamsPredicate = lambda offered, requested: True
    in_flight: int = 0
    last_seen: float = field(default_factory=time.monotonic)
    p50_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    success_rate: float = 1.0
    quarantined_until: float = 0.0
    sticky_sessions: set[str] = field(default_factory=set)

    @property
    def version(self) -> Version:
        return self.descriptor.version


@dataclass(frozen=True)
class RouteRequest:
    capability: CapabilityName
    version_req: Version
    body: dict[str, Any]
    caller: str
    trace_id: str
    session_id: str | None = None
    deadline_ms: int = 0
    stream: bool = False
