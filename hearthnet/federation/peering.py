"""Cross-community peering store and HTTP client (M14)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from hearthnet.federation.manifest import (
    FederationManifest,
    FederationProposal,
    ManifestError,
    _scope_from_dict,
    _scope_to_dict,
    co_sign_federation,
)

# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------


def _manifest_to_dict(m: FederationManifest) -> dict:
    return {
        "schema_version": m.schema_version,
        "federation_id": m.federation_id,
        "community_a_id": m.community_a_id,
        "community_a_name": m.community_a_name,
        "community_b_id": m.community_b_id,
        "community_b_name": m.community_b_name,
        "scope_a_to_b": _scope_to_dict(m.scope_a_to_b),
        "scope_b_to_a": _scope_to_dict(m.scope_b_to_a),
        "sig_a": m.sig_a,
        "sig_b": m.sig_b,
        "co_signers_a": m.co_signers_a,
        "co_signers_b": m.co_signers_b,
        "created_at": m.created_at,
        "expires_at": m.expires_at,
        "bootstrap_endpoints_a": m.bootstrap_endpoints_a,
        "bootstrap_endpoints_b": m.bootstrap_endpoints_b,
    }


def _manifest_from_dict(d: dict) -> FederationManifest:
    return FederationManifest(
        schema_version=int(d["schema_version"]),
        federation_id=d["federation_id"],
        community_a_id=d["community_a_id"],
        community_a_name=d.get("community_a_name", ""),
        community_b_id=d["community_b_id"],
        community_b_name=d.get("community_b_name", ""),
        scope_a_to_b=_scope_from_dict(d["scope_a_to_b"]),
        scope_b_to_a=_scope_from_dict(d["scope_b_to_a"]),
        sig_a=d.get("sig_a", ""),
        sig_b=d.get("sig_b", ""),
        co_signers_a=list(d.get("co_signers_a", [])),
        co_signers_b=list(d.get("co_signers_b", [])),
        created_at=int(d["created_at"]),
        expires_at=int(d["expires_at"]),
        bootstrap_endpoints_a=list(d.get("bootstrap_endpoints_a", [])),
        bootstrap_endpoints_b=list(d.get("bootstrap_endpoints_b", [])),
    )


def _proposal_to_dict(p: FederationProposal) -> dict:
    return {
        "community_a": p.community_a,
        "community_b": p.community_b,
        "scope_a": _scope_to_dict(p.scope_a),
        "scope_b": _scope_to_dict(p.scope_b),
        "bootstrap_a": p.bootstrap_a,
        "bootstrap_b": p.bootstrap_b,
        "proposed_at": p.proposed_at,
        "proposer_sig": p.proposer_sig,
    }


def _proposal_from_dict(d: dict) -> FederationProposal:
    return FederationProposal(
        community_a=d["community_a"],
        community_b=d["community_b"],
        scope_a=_scope_from_dict(d["scope_a"]),
        scope_b=_scope_from_dict(d["scope_b"]),
        bootstrap_a=list(d.get("bootstrap_a", [])),
        bootstrap_b=list(d.get("bootstrap_b", [])),
        proposed_at=int(d["proposed_at"]),
        proposer_sig=d.get("proposer_sig", ""),
    )


# ---------------------------------------------------------------------------
# FederationStore (SQLite)
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS federation_manifests (
    federation_id TEXT PRIMARY KEY,
    community_id TEXT NOT NULL,
    manifest_json TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fed_community ON federation_manifests (community_id);
"""


class FederationStore:
    """SQLite-backed store for active federation manifests."""

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self._db_path = str(db_path)
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def add_manifest(self, m: FederationManifest) -> None:
        """Insert or replace a federation manifest."""
        data = json.dumps(_manifest_to_dict(m))
        with self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO federation_manifests "
                "(federation_id, community_id, manifest_json, created_at, expires_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (m.federation_id, m.community_b_id, data, m.created_at, m.expires_at),
            )
            # Also index by community_a so lookups from either side work
            self._conn.execute(
                "INSERT OR REPLACE INTO federation_manifests "
                "(federation_id, community_id, manifest_json, created_at, expires_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    m.federation_id + "_rev",
                    m.community_a_id,
                    data,
                    m.created_at,
                    m.expires_at,
                ),
            )

    def get_manifest(self, community_id: str) -> FederationManifest | None:
        """Return the most recent active manifest for a community, or None."""
        import time

        now = int(time.time())
        row = self._conn.execute(
            "SELECT manifest_json FROM federation_manifests "
            "WHERE community_id = ? AND expires_at > ? "
            "ORDER BY created_at DESC LIMIT 1",
            (community_id, now),
        ).fetchone()
        if row is None:
            return None
        return _manifest_from_dict(json.loads(row[0]))

    def list_active(self) -> list[FederationManifest]:
        """Return all non-expired manifests (deduplicated by federation_id)."""
        import time

        now = int(time.time())
        rows = self._conn.execute(
            "SELECT DISTINCT manifest_json FROM federation_manifests WHERE expires_at > ?",
            (now,),
        ).fetchall()
        seen: set[str] = set()
        result: list[FederationManifest] = []
        for (row,) in rows:
            m = _manifest_from_dict(json.loads(row))
            if m.federation_id not in seen:
                seen.add(m.federation_id)
                result.append(m)
        return result

    def remove(self, federation_id: str) -> None:
        """Remove a federation manifest by its ID."""
        with self._conn:
            self._conn.execute(
                "DELETE FROM federation_manifests WHERE federation_id = ? OR federation_id = ?",
                (federation_id, federation_id + "_rev"),
            )


# ---------------------------------------------------------------------------
# PeeringClient — HTTP handshake helpers
# ---------------------------------------------------------------------------


class PeeringClient:
    """HTTP client for cross-community federation handshake.

    Uses the injected http_client which must implement .post(url, json=...) -> dict.
    """

    def __init__(self, http_client: Any) -> None:
        self._http = http_client

    def propose(self, remote_url: str, proposal: FederationProposal) -> FederationProposal:
        """Send a federation proposal to a peer community.

        Returns the peer's (possibly updated) proposal echo or raises ManifestError.
        """
        endpoint = remote_url.rstrip("/") + "/federation/propose"
        body = _proposal_to_dict(proposal)
        try:
            resp = self._http.post(endpoint, json=body)
        except Exception as exc:
            raise ManifestError(f"Peering propose failed: {exc}") from exc
        if isinstance(resp, dict) and "error" in resp:
            raise ManifestError(f"Remote rejected proposal: {resp['error']}")
        return _proposal_from_dict(resp)

    def co_sign(
        self,
        remote_url: str,
        proposal: FederationProposal,
        keypair: Any,
        role: str,
    ) -> FederationManifest:
        """Co-sign a proposal and submit it to produce a finalized manifest."""
        cosig = co_sign_federation(proposal, keypair, role)
        endpoint = remote_url.rstrip("/") + "/federation/cosign"
        body = {
            "proposal": _proposal_to_dict(proposal),
            "co_sig": cosig,
        }
        try:
            resp = self._http.post(endpoint, json=body)
        except Exception as exc:
            raise ManifestError(f"Peering co-sign failed: {exc}") from exc
        if isinstance(resp, dict) and "error" in resp:
            raise ManifestError(f"Remote rejected co-sign: {resp['error']}")
        return _manifest_from_dict(resp)
