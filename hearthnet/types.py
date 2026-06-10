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


# ── Phase 3 type aliases ─────────────────────────────────────────────────────
from typing import NewType

ShardID = NewType("ShardID", str)           # "<model_id>:<lo>-<hi>[:tier]"
ExpertID = NewType("ExpertID", str)         # "human:..." | "model:..." | "service:..." | "external:..."
ExpertKind = Literal["human", "model", "service", "external"]
ClaimID = NewType("ClaimID", str)           # base32 of SHA-256 canonical claim
SourceID = NewType("SourceID", str)
EvidenceLevel = Literal["unverified", "cited", "cross_referenced", "attested", "disputed"]
RoundID = NewType("RoundID", str)           # ULID — fedlearn round
LoraBeaconID = NewType("LoraBeaconID", str) # 8-byte hex, hardware-issued
LoraDeviceID = NewType("LoraDeviceID", str)
AlertID = NewType("AlertID", str)           # ULID
AlertSeverity = Literal["info", "advisory", "warning", "emergency", "extreme"]
AckStatus = Literal["received", "acting", "need_help", "standing_down", "mistaken"]


@dataclass(frozen=True)
class ProtocolVersion:
    major: int
    minor: int
    patch: int
    suffix: str = ""

    def __str__(self) -> str:
        base = f"{self.major}.{self.minor}.{self.patch}"
        return f"{base}-{self.suffix}" if self.suffix else base
