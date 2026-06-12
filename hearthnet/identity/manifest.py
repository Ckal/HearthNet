from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

UTC = UTC

from hearthnet.identity.keys import (
    IdentityError,
    KeyPair,
    parse_node_id,
    sign_payload,
    verify_payload,
)

try:
    import nacl.signing

    _NACL_AVAILABLE = True
except ImportError:  # pragma: no cover
    _NACL_AVAILABLE = False

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ManifestError(Exception):
    """Raised for manifest validation failures."""

    def __init__(self, code: str, reason: str = "") -> None:
        super().__init__(reason or code)
        self.code = code
        self.reason = reason


# ---------------------------------------------------------------------------
# Value types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Endpoint:
    transport: str
    host: str
    port: int


@dataclass(frozen=True)
class HardwareSpec:
    gpu: str | None
    ram_gb: float
    cpu_cores: int
    disk_free_gb: float


@dataclass(frozen=True)
class CapabilitySpec:
    name: str
    version: str
    stability: str
    params: dict
    max_concurrent: int


# ---------------------------------------------------------------------------
# NodeManifest
# ---------------------------------------------------------------------------

_NODE_MANIFEST_TTL_SECONDS = 30
_COMMUNITY_MANIFEST_TTL_SECONDS = 86400

_REQUIRED_NODE_FIELDS = {
    "version",
    "node_id",
    "display_name",
    "community_id",
    "profile",
    "endpoints",
    "capabilities",
    "issued_at",
    "expires_at",
    "contract_version",
    "signature",
}

_REQUIRED_COMMUNITY_FIELDS = {
    "version",
    "community_id",
    "name",
    "root_node_id",
    "members",
    "policy",
    "issued_at",
    "expires_at",
    "contract_version",
    "signature",
}


def _parse_rfc3339(s: str) -> datetime:
    """Parse RFC 3339 UTC timestamp."""
    # Accept trailing Z or +00:00
    s = s.rstrip("Z")
    if "+" in s:
        s = s[: s.index("+")]
    return datetime.fromisoformat(s).replace(tzinfo=UTC)


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _rfc3339(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class NodeManifest:
    version: int
    node_id: str
    display_name: str
    community_id: str
    profile: str
    endpoints: list
    capabilities: list
    hardware: HardwareSpec | None
    issued_at: str
    expires_at: str
    contract_version: str
    signature: str

    def is_expired(self, now: datetime | None = None) -> bool:
        ts = now or _now_utc()
        try:
            exp = _parse_rfc3339(self.expires_at)
        except (ValueError, AttributeError):
            return True
        return ts >= exp

    def as_dict(self) -> dict:
        d: dict[str, Any] = {
            "version": self.version,
            "node_id": self.node_id,
            "display_name": self.display_name,
            "community_id": self.community_id,
            "profile": self.profile,
            "endpoints": [
                {"transport": e.transport, "host": e.host, "port": e.port} for e in self.endpoints
            ],
            "capabilities": [
                {
                    "name": c.name,
                    "version": c.version,
                    "stability": c.stability,
                    "params": c.params,
                    "max_concurrent": c.max_concurrent,
                }
                for c in self.capabilities
            ],
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "contract_version": self.contract_version,
            "signature": self.signature,
        }
        if self.hardware is not None:
            d["hardware"] = {
                "gpu": self.hardware.gpu,
                "ram_gb": self.hardware.ram_gb,
                "cpu_cores": self.hardware.cpu_cores,
                "disk_free_gb": self.hardware.disk_free_gb,
            }
        return d


@dataclass(frozen=True)
class RevokedEntry:
    """A revoked member entry in a community manifest."""
    node_id: str
    revoked_at: str
    reason: str = ""


@dataclass(frozen=True)
class CommunityMember:
    """A member record in a community manifest."""
    node_id: str
    display_name: str
    level: str  # "root" | "trusted" | "moderator" | "member"
    joined_at: str
    invited_by: str = ""


@dataclass(frozen=True)
class CommunityPolicy:
    """Community governance policy embedded in CommunityManifest."""
    allow_public_join: bool = False
    require_invite: bool = True
    max_members: int = 500
    min_trust_for_invite: str = "member"


@dataclass(frozen=True)
class CommunityManifest:
    version: int
    community_id: str
    name: str
    root_node_id: str
    members: list
    policy: dict
    issued_at: str
    expires_at: str
    contract_version: str
    signature: str

    def is_expired(self, now: datetime | None = None) -> bool:
        ts = now or _now_utc()
        try:
            exp = _parse_rfc3339(self.expires_at)
        except (ValueError, AttributeError):
            return True
        return ts >= exp

    def as_dict(self) -> dict:
        return {
            "version": self.version,
            "community_id": self.community_id,
            "name": self.name,
            "root_node_id": self.root_node_id,
            "members": list(self.members),
            "policy": dict(self.policy),
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "contract_version": self.contract_version,
            "signature": self.signature,
        }


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def build_node_manifest(
    kp: KeyPair,
    display_name: str,
    community_id: str,
    profile: str,
    endpoints: list[Endpoint],
    capabilities: list[CapabilitySpec],
    hardware: HardwareSpec | None = None,
) -> NodeManifest:
    now = _now_utc()
    issued_at = _rfc3339(now)
    expires_at = _rfc3339(now + timedelta(seconds=_NODE_MANIFEST_TTL_SECONDS))
    payload: dict[str, Any] = {
        "version": 1,
        "node_id": kp.node_id_full,
        "display_name": display_name,
        "community_id": community_id,
        "profile": profile,
        "endpoints": [
            {"transport": e.transport, "host": e.host, "port": e.port} for e in endpoints
        ],
        "capabilities": [
            {
                "name": c.name,
                "version": c.version,
                "stability": c.stability,
                "params": c.params,
                "max_concurrent": c.max_concurrent,
            }
            for c in capabilities
        ],
        "issued_at": issued_at,
        "expires_at": expires_at,
        "contract_version": "1.0",
    }
    if hardware is not None:
        payload["hardware"] = {
            "gpu": hardware.gpu,
            "ram_gb": hardware.ram_gb,
            "cpu_cores": hardware.cpu_cores,
            "disk_free_gb": hardware.disk_free_gb,
        }
    signed = sign_payload(payload, kp)
    return NodeManifest(
        version=signed["version"],
        node_id=signed["node_id"],
        display_name=signed["display_name"],
        community_id=signed["community_id"],
        profile=signed["profile"],
        endpoints=[
            Endpoint(transport=e["transport"], host=e["host"], port=e["port"])
            for e in signed["endpoints"]
        ],
        capabilities=[
            CapabilitySpec(
                name=c["name"],
                version=c["version"],
                stability=c["stability"],
                params=c["params"],
                max_concurrent=c["max_concurrent"],
            )
            for c in signed["capabilities"]
        ],
        hardware=hardware,
        issued_at=signed["issued_at"],
        expires_at=signed["expires_at"],
        contract_version=signed["contract_version"],
        signature=signed["signature"],
    )


def verify_node_manifest(manifest_dict: dict) -> NodeManifest:
    """Verify signature and expiry, return NodeManifest."""
    missing = _REQUIRED_NODE_FIELDS - set(manifest_dict.keys())
    if missing:
        raise ManifestError("missing_field", reason=f"Missing fields: {missing}")
    node_id = manifest_dict.get("node_id", "")
    try:
        vk_bytes = parse_node_id(node_id)
    except ValueError as exc:
        raise ManifestError("schema_error", reason=str(exc)) from exc
    if not _NACL_AVAILABLE:
        raise ManifestError("invalid_signature", reason="PyNaCl not installed")
    try:
        vk = nacl.signing.VerifyKey(vk_bytes)
    except Exception as exc:
        raise ManifestError("schema_error", reason=str(exc)) from exc
    try:
        verify_payload(manifest_dict, vk)
    except IdentityError as exc:
        raise ManifestError("invalid_signature", reason=exc.reason) from exc
    # Check expiry
    expires_at = manifest_dict.get("expires_at", "")
    try:
        exp = _parse_rfc3339(expires_at)
    except (ValueError, AttributeError) as exc:
        raise ManifestError("schema_error", reason=f"Invalid expires_at: {expires_at}") from exc
    if _now_utc() >= exp:
        raise ManifestError("expired", reason=f"Manifest expired at {expires_at}")
    hw_dict = manifest_dict.get("hardware")
    hardware = (
        HardwareSpec(
            gpu=hw_dict.get("gpu"),
            ram_gb=hw_dict["ram_gb"],
            cpu_cores=hw_dict["cpu_cores"],
            disk_free_gb=hw_dict["disk_free_gb"],
        )
        if hw_dict
        else None
    )
    return NodeManifest(
        version=manifest_dict["version"],
        node_id=manifest_dict["node_id"],
        display_name=manifest_dict["display_name"],
        community_id=manifest_dict["community_id"],
        profile=manifest_dict["profile"],
        endpoints=[
            Endpoint(transport=e["transport"], host=e["host"], port=e["port"])
            for e in manifest_dict["endpoints"]
        ],
        capabilities=[
            CapabilitySpec(
                name=c["name"],
                version=c["version"],
                stability=c["stability"],
                params=c["params"],
                max_concurrent=c["max_concurrent"],
            )
            for c in manifest_dict["capabilities"]
        ],
        hardware=hardware,
        issued_at=manifest_dict["issued_at"],
        expires_at=manifest_dict["expires_at"],
        contract_version=manifest_dict["contract_version"],
        signature=manifest_dict["signature"],
    )


def build_community_manifest(
    kp: KeyPair,
    name: str,
    members: list[str],
    policy: dict,
) -> CommunityManifest:
    now = _now_utc()
    issued_at = _rfc3339(now)
    expires_at = _rfc3339(now + timedelta(seconds=_COMMUNITY_MANIFEST_TTL_SECONDS))
    community_id = kp.node_id_full
    payload: dict[str, Any] = {
        "version": 1,
        "community_id": community_id,
        "name": name,
        "root_node_id": kp.node_id_full,
        "members": list(members),
        "policy": dict(policy),
        "issued_at": issued_at,
        "expires_at": expires_at,
        "contract_version": "1.0",
    }
    signed = sign_payload(payload, kp)
    return CommunityManifest(
        version=signed["version"],
        community_id=signed["community_id"],
        name=signed["name"],
        root_node_id=signed["root_node_id"],
        members=signed["members"],
        policy=signed["policy"],
        issued_at=signed["issued_at"],
        expires_at=signed["expires_at"],
        contract_version=signed["contract_version"],
        signature=signed["signature"],
    )


def verify_community_manifest(manifest_dict: dict) -> CommunityManifest:
    """Verify signature and expiry, return CommunityManifest."""
    missing = _REQUIRED_COMMUNITY_FIELDS - set(manifest_dict.keys())
    if missing:
        raise ManifestError("missing_field", reason=f"Missing fields: {missing}")
    root_node_id = manifest_dict.get("root_node_id", "")
    try:
        vk_bytes = parse_node_id(root_node_id)
    except ValueError as exc:
        raise ManifestError("schema_error", reason=str(exc)) from exc
    if not _NACL_AVAILABLE:
        raise ManifestError("invalid_signature", reason="PyNaCl not installed")
    try:
        vk = nacl.signing.VerifyKey(vk_bytes)
    except Exception as exc:
        raise ManifestError("schema_error", reason=str(exc)) from exc
    try:
        verify_payload(manifest_dict, vk)
    except IdentityError as exc:
        raise ManifestError("invalid_signature", reason=exc.reason) from exc
    expires_at = manifest_dict.get("expires_at", "")
    try:
        exp = _parse_rfc3339(expires_at)
    except (ValueError, AttributeError) as exc:
        raise ManifestError("schema_error", reason=f"Invalid expires_at: {expires_at}") from exc
    if _now_utc() >= exp:
        raise ManifestError("expired", reason=f"Manifest expired at {expires_at}")
    return CommunityManifest(
        version=manifest_dict["version"],
        community_id=manifest_dict["community_id"],
        name=manifest_dict["name"],
        root_node_id=manifest_dict["root_node_id"],
        members=manifest_dict["members"],
        policy=manifest_dict["policy"],
        issued_at=manifest_dict["issued_at"],
        expires_at=manifest_dict["expires_at"],
        contract_version=manifest_dict["contract_version"],
        signature=manifest_dict["signature"],
    )
