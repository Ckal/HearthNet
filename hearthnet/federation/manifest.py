"""Federation manifest builder and verifier (M14)."""
from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass
from typing import Any

try:
    import nacl.bindings
    import nacl.exceptions

    _NACL_AVAILABLE = True
except ImportError:  # pragma: no cover
    nacl = None  # type: ignore[assignment]
    _NACL_AVAILABLE = False


class ManifestError(Exception):
    """Raised for federation manifest validation failures."""


# ---------------------------------------------------------------------------
# Value types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FederationScope:
    """What one community grants the other."""

    capabilities: list[str]
    data_visibility: str = "public_corpora_only"  # "public_corpora_only"|"members_only"|"open"


@dataclass(frozen=True)
class FederationManifest:
    """A bilateral federation agreement between two communities."""

    schema_version: int
    federation_id: str
    community_a_id: str
    community_a_name: str
    community_b_id: str
    community_b_name: str
    scope_a_to_b: FederationScope   # what A grants B
    scope_b_to_a: FederationScope   # what B grants A
    sig_a: str                       # Ed25519 sig from anchor of community A
    sig_b: str                       # Ed25519 sig from anchor of community B
    co_signers_a: list[str]          # additional anchor signatures from community A
    co_signers_b: list[str]          # additional anchor signatures from community B
    created_at: int                  # unix seconds
    expires_at: int                  # unix seconds
    bootstrap_endpoints_a: list[str]
    bootstrap_endpoints_b: list[str]

    def is_expired(self, now: int | None = None) -> bool:
        ts = now if now is not None else int(time.time())
        return ts >= self.expires_at


@dataclass(frozen=True)
class FederationProposal:
    """A draft federation proposal from community A to community B."""

    community_a: str              # community_id of proposer
    community_b: str              # community_id of target
    scope_a: FederationScope      # scope A proposes to grant B
    scope_b: FederationScope      # scope A requests from B
    bootstrap_a: list[str]        # endpoints for community A
    bootstrap_b: list[str]        # expected endpoints for community B
    proposed_at: int              # unix seconds
    proposer_sig: str             # Ed25519 sig over the proposal body by an anchor of A


# ---------------------------------------------------------------------------
# Encoding helpers
# ---------------------------------------------------------------------------


def _b64url_encode(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    pad = 4 - len(s) % 4
    if pad != 4:
        s += "=" * pad
    return base64.urlsafe_b64decode(s)


def _scope_to_dict(s: FederationScope) -> dict:
    return {"capabilities": list(s.capabilities), "data_visibility": s.data_visibility}


def _scope_from_dict(d: dict) -> FederationScope:
    return FederationScope(
        capabilities=list(d.get("capabilities", [])),
        data_visibility=d.get("data_visibility", "public_corpora_only"),
    )


def _proposal_body(proposal: FederationProposal) -> bytes:
    """Canonical bytes for signing a proposal."""
    body = {
        "community_a": proposal.community_a,
        "community_b": proposal.community_b,
        "scope_a": _scope_to_dict(proposal.scope_a),
        "scope_b": _scope_to_dict(proposal.scope_b),
        "bootstrap_a": proposal.bootstrap_a,
        "bootstrap_b": proposal.bootstrap_b,
        "proposed_at": proposal.proposed_at,
    }
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode()


def _manifest_body(manifest: FederationManifest) -> bytes:
    """Canonical bytes for signing a manifest (excludes sig_a, sig_b, co_signers)."""
    body = {
        "schema_version": manifest.schema_version,
        "federation_id": manifest.federation_id,
        "community_a_id": manifest.community_a_id,
        "community_a_name": manifest.community_a_name,
        "community_b_id": manifest.community_b_id,
        "community_b_name": manifest.community_b_name,
        "scope_a_to_b": _scope_to_dict(manifest.scope_a_to_b),
        "scope_b_to_a": _scope_to_dict(manifest.scope_b_to_a),
        "created_at": manifest.created_at,
        "expires_at": manifest.expires_at,
        "bootstrap_endpoints_a": manifest.bootstrap_endpoints_a,
        "bootstrap_endpoints_b": manifest.bootstrap_endpoints_b,
    }
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode()


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------


def build_federation_proposal(
    our_manifest: Any,
    our_keypair: Any,
    their_community_id: str,
    their_community_name: str,
    scope_we_grant: FederationScope,
    scope_they_grant: FederationScope,
    bootstrap_endpoints: list[str],
) -> FederationProposal:
    """Create a signed federation proposal to send to a peer community."""
    if not _NACL_AVAILABLE:
        raise ManifestError("PyNaCl is required for federation. Install pynacl.")

    our_community_id = getattr(our_manifest, "community_id", "")
    now = int(time.time())

    # Build an unsigned proposal first to produce the body bytes for signing
    unsigned_proposal = FederationProposal(
        community_a=our_community_id,
        community_b=their_community_id,
        scope_a=scope_we_grant,
        scope_b=scope_they_grant,
        bootstrap_a=bootstrap_endpoints,
        bootstrap_b=[],
        proposed_at=now,
        proposer_sig="",
    )
    body = _proposal_body(unsigned_proposal)
    try:
        signed = our_keypair.signing_key.sign(body)
        sig_b64 = _b64url_encode(signed.signature)
    except Exception as exc:
        raise ManifestError(f"Signing proposal failed: {exc}") from exc

    return FederationProposal(
        community_a=our_community_id,
        community_b=their_community_id,
        scope_a=scope_we_grant,
        scope_b=scope_they_grant,
        bootstrap_a=bootstrap_endpoints,
        bootstrap_b=[],
        proposed_at=now,
        proposer_sig=sig_b64,
    )


def co_sign_federation(proposal: FederationProposal, keypair: Any, role: str) -> dict:
    """Co-sign a federation proposal on behalf of a community anchor.

    Returns {signed_by: node_id, signature: b64url, role: str}.
    """
    if not _NACL_AVAILABLE:
        raise ManifestError("PyNaCl is required. Install pynacl.")

    from hearthnet.identity.keys import full_node_id

    body = _proposal_body(proposal)
    try:
        signed = keypair.signing_key.sign(body)
        sig_b64 = _b64url_encode(signed.signature)
    except Exception as exc:
        raise ManifestError(f"Co-signing failed: {exc}") from exc

    node_id = full_node_id(bytes(keypair.verify_key))
    return {"signed_by": node_id, "signature": sig_b64, "role": role}


def finalize_federation_manifest(
    proposal: FederationProposal,
    sig_a: str,
    sig_b: str,
    community_a_name: str = "",
    community_b_name: str = "",
    ttl_seconds: int = 365 * 24 * 3600,
) -> FederationManifest:
    """Combine a proposal and both anchor signatures into a finalized manifest."""
    from hearthnet.events.types import new_ulid

    now = int(time.time())
    return FederationManifest(
        schema_version=1,
        federation_id=new_ulid(),
        community_a_id=proposal.community_a,
        community_a_name=community_a_name,
        community_b_id=proposal.community_b,
        community_b_name=community_b_name,
        scope_a_to_b=proposal.scope_a,
        scope_b_to_a=proposal.scope_b,
        sig_a=sig_a,
        sig_b=sig_b,
        co_signers_a=[],
        co_signers_b=[],
        created_at=now,
        expires_at=now + ttl_seconds,
        bootstrap_endpoints_a=proposal.bootstrap_a,
        bootstrap_endpoints_b=proposal.bootstrap_b,
    )


def verify_federation_manifest(
    manifest: FederationManifest,
    community_a_verify_key: Any,
    community_b_verify_key: Any,
) -> None:
    """Verify both anchor signatures on a manifest. Raises ManifestError if invalid."""
    if not _NACL_AVAILABLE:
        raise ManifestError("PyNaCl is required. Install pynacl.")

    body = _manifest_body(manifest)

    for label, sig_str, vk in [
        ("community_a", manifest.sig_a, community_a_verify_key),
        ("community_b", manifest.sig_b, community_b_verify_key),
    ]:
        if not sig_str:
            raise ManifestError(f"Missing signature for {label}")
        try:
            import nacl.exceptions

            sig_bytes = _b64url_decode(sig_str)
            vk.verify(body, sig_bytes)
        except nacl.exceptions.BadSignatureError as exc:
            raise ManifestError(f"Invalid signature for {label}: {exc}") from exc
        except Exception as exc:
            raise ManifestError(f"Signature verification error for {label}: {exc}") from exc
