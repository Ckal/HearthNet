"""M31 — Civil Defense (NRW Bevölkerungsschutz pilot, experimental Phase 3).

Bridges HearthNet with THW/DRK/Feuerwehr/KatS role structures.
Produces tamper-evident audit trails for incident coordination.
Gated by config.research.civil_defense = True.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

# NRW role taxonomy
NRW_ROLES = {
    "thw_helferin": "THW Helferin/Helfer",
    "thw_gruppenfuehrer": "THW Gruppenführer",
    "drk_ersthelfer": "DRK Ersthelfer",
    "drk_sanitaeter": "DRK Sanitäter",
    "feuerwehr_angehoeriger": "Feuerwehr-Angehöriger",
    "feuerwehr_fuehrungskraft": "Feuerwehr-Führungskraft",
    "kats_koordinator": "KatS-Koordinator",
    "kats_leiterin": "KatS-Leiterin",
    "bevoelkerungsschutz_beauftragte": "Bevölkerungsschutzbeauftragte(r)",
}


@dataclass(frozen=True)
class AlertSeverity:
    INFORMATION = "information"
    WARNING = "warning"
    ALERT = "alert"
    EMERGENCY = "emergency"


@dataclass(frozen=True)
class RoleCertificate:
    """A role certificate issued by an authority for a community member."""

    cert_id: str
    role_key: str  # key from NRW_ROLES
    role_label: str
    holder_node_id: str
    issuer_node_id: str
    community_id: str
    region: str = "NRW"
    issued_at: float = field(default_factory=time.time)
    expires_at: float | None = None
    issuer_signature: bytes = b""

    def is_expired(self, now: float | None = None) -> bool:
        if self.expires_at is None:
            return False
        return (now or time.time()) > self.expires_at

    def role_name(self) -> str:
        return NRW_ROLES.get(self.role_key, self.role_label)


@dataclass(frozen=True)
class Alert:
    """A civil-defense alert with full provenance."""

    alert_id: str
    severity: str  # AlertSeverity constant
    title: str
    body: str
    area_description: str  # e.g. "Issum, Kreis Kleve, NRW"
    issuer_node_id: str
    issuer_role_cert_id: str | None
    community_id: str
    event_log_id: str | None = None  # optional backlink to event log entry
    issued_at: float = field(default_factory=time.time)
    expires_at: float | None = None
    issuer_signature: bytes = b""


class AuditChain:
    """Tamper-evident append-only audit log for civil-defense operations.

    Each entry is a JSON-serialised dict with a backlink hash for chain integrity.
    For production use, entries should be stored in the event log (X02) with
    Ed25519 signatures to satisfy legal audit retention requirements.
    """

    def __init__(self) -> None:
        self._entries: list[dict] = []
        self._head_hash: str = "0" * 64

    def _hash_entry(self, entry: dict) -> str:
        serialised = json.dumps(entry, sort_keys=True, ensure_ascii=True)
        return hashlib.sha256(serialised.encode()).hexdigest()

    def append(self, entry_type: str, actor_node_id: str, payload: dict[str, Any]) -> str:
        entry = {
            "entry_id": str(uuid.uuid4()),
            "entry_type": entry_type,
            "actor": actor_node_id,
            "payload": payload,
            "timestamp": time.time(),
            "prev_hash": self._head_hash,
        }
        entry_hash = self._hash_entry(entry)
        entry["hash"] = entry_hash
        self._entries.append(entry)
        self._head_hash = entry_hash
        return entry_hash

    def verify_integrity(self) -> bool:
        """Walk the chain and verify all backlinks."""
        prev = "0" * 64
        for entry in self._entries:
            if entry.get("prev_hash") != prev:
                return False
            expected_hash = entry["hash"]
            entry_copy = {k: v for k, v in entry.items() if k != "hash"}
            if self._hash_entry(entry_copy) != expected_hash:
                return False
            prev = expected_hash
        return True

    def export(self) -> list[dict]:
        return list(self._entries)

    def length(self) -> int:
        return len(self._entries)


class CivilDefenseService:
    """Civil-defense pilot service for NRW.

    Registers capabilities:
      civdef.alert.issue@1.0   — publish a signed alert
      civdef.alert.list@1.0    — list active alerts
      civdef.cert.verify@1.0   — verify a role certificate
      civdef.audit.export@1.0  — export tamper-evident audit chain

    Only active when config.research.civil_defense = True.
    """

    def __init__(self, keypair=None, bus=None) -> None:
        self._keypair = keypair
        self._bus = bus
        self._alerts: dict[str, Alert] = {}
        self._certs: dict[str, RoleCertificate] = {}
        self._audit = AuditChain()

    def issue_alert(
        self,
        severity: str,
        title: str,
        body: str,
        area: str,
        role_cert_id: str | None = None,
        community_id: str = "",
        expires_in_hours: float | None = 24.0,
    ) -> Alert:
        node_id = getattr(self._keypair, "node_id_short", "unknown")
        alert = Alert(
            alert_id=str(uuid.uuid4()),
            severity=severity,
            title=title,
            body=body,
            area_description=area,
            issuer_node_id=node_id,
            issuer_role_cert_id=role_cert_id,
            community_id=community_id,
            expires_at=time.time() + expires_in_hours * 3600 if expires_in_hours else None,
        )
        self._alerts[alert.alert_id] = alert
        self._audit.append(
            "alert.issued",
            node_id,
            {
                "alert_id": alert.alert_id,
                "severity": alert.severity,
                "title": alert.title,
            },
        )
        return alert

    def list_active_alerts(self, now: float | None = None) -> list[Alert]:
        now = now or time.time()
        return [a for a in self._alerts.values() if a.expires_at is None or a.expires_at > now]

    def register_cert(self, cert: RoleCertificate) -> None:
        self._certs[cert.cert_id] = cert
        self._audit.append(
            "cert.registered",
            cert.issuer_node_id,
            {"cert_id": cert.cert_id, "role": cert.role_key, "holder": cert.holder_node_id},
        )

    def verify_cert(self, cert_id: str) -> dict:
        cert = self._certs.get(cert_id)
        if cert is None:
            return {"valid": False, "reason": "cert_not_found"}
        if cert.is_expired():
            return {"valid": False, "reason": "cert_expired", "cert_id": cert_id}
        return {
            "valid": True,
            "role": cert.role_name(),
            "holder": cert.holder_node_id,
            "expires_at": cert.expires_at,
        }

    def export_audit(self) -> dict:
        return {
            "entries": self._audit.export(),
            "chain_valid": self._audit.verify_integrity(),
            "length": self._audit.length(),
        }

    # ── Capability-bus adapter (registered only under research=True) ────────

    name = "civdef"
    version = "1.0"

    def capabilities(self) -> list[tuple]:
        from hearthnet.bus.capability import CapabilityDescriptor

        return [
            (
                CapabilityDescriptor(
                    name="civdef.alert.issue",
                    version=(1, 0),
                    stability="experimental",
                    trust_required="trusted",
                ),
                self.handle_issue,
                None,
            ),
            (
                CapabilityDescriptor(
                    name="civdef.alert.list",
                    version=(1, 0),
                    stability="experimental",
                    idempotent=True,
                ),
                self.handle_list,
                None,
            ),
            (
                CapabilityDescriptor(
                    name="civdef.cert.verify",
                    version=(1, 0),
                    stability="experimental",
                    idempotent=True,
                ),
                self.handle_verify,
                None,
            ),
            (
                CapabilityDescriptor(
                    name="civdef.audit.export",
                    version=(1, 0),
                    stability="experimental",
                    idempotent=True,
                ),
                self.handle_audit,
                None,
            ),
        ]

    def register(self, bus: Any) -> None:
        self._bus = bus
        for cap, handler, predicate in self.capabilities():
            bus.register_capability(cap, handler, predicate)

    @staticmethod
    def _alert_to_dict(alert: Alert) -> dict[str, Any]:
        return {
            "alert_id": alert.alert_id,
            "severity": alert.severity,
            "title": alert.title,
            "body": alert.body,
            "area": alert.area_description,
            "issuer_node_id": alert.issuer_node_id,
            "community_id": alert.community_id,
            "issued_at": alert.issued_at,
            "expires_at": alert.expires_at,
        }

    async def handle_issue(self, req: Any) -> dict:
        inp = req.body.get("input", {})
        title = str(inp.get("title", ""))
        body = str(inp.get("body", ""))
        area = str(inp.get("area", ""))
        if not title or not area:
            return {"error": "bad_request", "message": "title and area are required"}
        alert = self.issue_alert(
            severity=str(inp.get("severity", AlertSeverity.WARNING)),
            title=title,
            body=body,
            area=area,
            role_cert_id=inp.get("role_cert_id"),
            community_id=str(inp.get("community_id", "")),
            expires_in_hours=inp.get("expires_in_hours", 24.0),
        )
        return {"output": {"alert": self._alert_to_dict(alert)}, "meta": {}}

    async def handle_list(self, req: Any) -> dict:
        alerts = [self._alert_to_dict(a) for a in self.list_active_alerts()]
        return {"output": {"alerts": alerts}, "meta": {"count": len(alerts)}}

    async def handle_verify(self, req: Any) -> dict:
        cert_id = str(req.body.get("input", {}).get("cert_id", ""))
        return {"output": self.verify_cert(cert_id), "meta": {}}

    async def handle_audit(self, req: Any) -> dict:
        return {"output": self.export_audit(), "meta": {}}
