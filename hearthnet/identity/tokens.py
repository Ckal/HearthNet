from __future__ import annotations

"""tokens.py — Phase 2 stub for capability tokens.

All functions raise NotImplementedError. Implement in Phase 2.
"""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CapabilityToken:
    """Stub for a signed capability token (Phase 2)."""

    token_id: str
    issuer_node_id: str
    subject_node_id: str
    capability: str
    issued_at: str
    expires_at: str
    signature: str


def issue_token(
    issuer_kp: Any,
    subject_node_id: str,
    capability: str,
    ttl_seconds: int = 300,
) -> CapabilityToken:
    """Issue a signed capability token. Phase 2 — not yet implemented."""
    raise NotImplementedError("CapabilityToken issuance is a Phase 2 feature.")


def verify_token(token: CapabilityToken) -> bool:
    """Verify a capability token's signature and expiry. Phase 2 — not yet implemented."""
    raise NotImplementedError("CapabilityToken verification is a Phase 2 feature.")


def revoke_token(token_id: str) -> None:
    """Revoke a capability token by ID. Phase 2 — not yet implemented."""
    raise NotImplementedError("CapabilityToken revocation is a Phase 2 feature.")
