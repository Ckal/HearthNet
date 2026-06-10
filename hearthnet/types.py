from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

NodeID = str
CommunityID = str
CapabilityName = str
Version = tuple[int, int]
TraceID = str
WallClock = str
TrustLevel = Literal["unknown", "member", "trusted", "anchor"]
Profile = Literal["anchor", "hearth", "spark", "bridge"]
Stability = Literal["experimental", "beta", "stable"]
ErrorCode = Literal[
    "not_found",
    "capacity_exceeded",
    "schema_mismatch",
    "unauthorized",
    "revoked",
    "internal_error",
    "not_implemented",
    "timeout",
    "partition",
    "invalid_signature",
    "expired",
    "rate_limited",
    "bad_request",
]


@dataclass(frozen=True)
class Endpoint:
    transport: str
    host: str
    port: int


class HearthNetError(Exception):
    def __init__(self, code: ErrorCode, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code
        self.message = message or code
