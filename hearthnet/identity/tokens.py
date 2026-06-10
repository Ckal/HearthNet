"""hearthnet/identity/tokens.py — Capability tokens (M16, Phase 2).

Token format: hntoken://v1/<b64url(header)>.<b64url(payload)>.<b64url(sig)>
"""
from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass
from typing import Any

try:
    import nacl.public  # noqa: F401 — presence check only

    _NACL_AVAILABLE = True
except ImportError:  # pragma: no cover
    _NACL_AVAILABLE = False


class TokenError(Exception):
    """Raised for all token-layer failures."""


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TokenScope:
    """Scope granted by a capability token."""

    capabilities: list[str]
    max_uses: int | None = None
    max_calls_total: int | None = None


@dataclass(frozen=True)
class CapabilityToken:
    """A signed Ed25519 capability token."""

    iss: str        # issuer node_id (full form "ed25519:…")
    sub: str        # subject node_id or "*" for bearer token
    aud: str        # audience community_id or ""
    iat: int        # issued-at unix seconds
    exp: int        # expires-at unix seconds
    nbf: int        # not-before unix seconds
    scope: TokenScope
    jti: str        # unique token ID (ULID)
    issued_via: str  # "federation"|"onboarding"|"manual"|"relay"


# ---------------------------------------------------------------------------
# Encoding helpers
# ---------------------------------------------------------------------------

_TOKEN_SCHEME = "hntoken://v1/"

_HEADER = json.dumps({"alg": "EdDSA", "typ": "hntoken", "v": 1}, separators=(",", ":"))
_HEADER_B64 = base64.urlsafe_b64encode(_HEADER.encode()).rstrip(b"=").decode("ascii")


def _b64url_encode(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    pad = 4 - len(s) % 4
    if pad != 4:
        s += "=" * pad
    return base64.urlsafe_b64decode(s)


def _scope_to_dict(scope: TokenScope) -> dict[str, Any]:
    return {
        "capabilities": list(scope.capabilities),
        "max_uses": scope.max_uses,
        "max_calls_total": scope.max_calls_total,
    }


def _scope_from_dict(d: dict[str, Any]) -> TokenScope:
    return TokenScope(
        capabilities=list(d.get("capabilities", [])),
        max_uses=d.get("max_uses"),
        max_calls_total=d.get("max_calls_total"),
    )


def _payload_to_dict(tok: CapabilityToken) -> dict[str, Any]:
    return {
        "iss": tok.iss,
        "sub": tok.sub,
        "aud": tok.aud,
        "iat": tok.iat,
        "exp": tok.exp,
        "nbf": tok.nbf,
        "scope": _scope_to_dict(tok.scope),
        "jti": tok.jti,
        "issued_via": tok.issued_via,
    }


# ---------------------------------------------------------------------------
# Issue
# ---------------------------------------------------------------------------


def issue_token(
    issuer_kp: Any,
    subject_node_id: str,
    audience: str,
    scope: TokenScope,
    ttl_seconds: int = 3600,
    issued_via: str = "manual",
) -> tuple[CapabilityToken, str]:
    """Issue a signed capability token.

    Returns (CapabilityToken, encoded_token_string).
    """
    if not _NACL_AVAILABLE:
        raise TokenError("PyNaCl is required for token issuance. Install pynacl.")

    from hearthnet.events.types import new_ulid
    from hearthnet.identity.keys import full_node_id

    now = int(time.time())
    jti = new_ulid()
    iss = full_node_id(bytes(issuer_kp.verify_key))

    tok = CapabilityToken(
        iss=iss,
        sub=subject_node_id,
        aud=audience,
        iat=now,
        exp=now + ttl_seconds,
        nbf=now,
        scope=scope,
        jti=jti,
        issued_via=issued_via,
    )
    payload_bytes = json.dumps(_payload_to_dict(tok), separators=(",", ":")).encode()
    payload_b64 = _b64url_encode(payload_bytes)
    signing_input = f"{_HEADER_B64}.{payload_b64}".encode()

    try:
        signed = issuer_kp.signing_key.sign(signing_input)
        sig_b64 = _b64url_encode(signed.signature)
    except Exception as exc:
        raise TokenError(f"Signing failed: {exc}") from exc

    encoded = encode_token(tok, sig_b64)
    return tok, encoded


def encode_token(tok: CapabilityToken, signature_b64: str) -> str:
    """Encode a CapabilityToken + pre-computed signature to the hntoken:// string."""
    payload_bytes = json.dumps(_payload_to_dict(tok), separators=(",", ":")).encode()
    payload_b64 = _b64url_encode(payload_bytes)
    return f"{_TOKEN_SCHEME}{_HEADER_B64}.{payload_b64}.{signature_b64}"


# ---------------------------------------------------------------------------
# Decode (structural only, no sig verify)
# ---------------------------------------------------------------------------


def decode_token(text: str) -> CapabilityToken:
    """Parse an hntoken:// string. Validates structure; does NOT verify the signature."""
    if not text.startswith(_TOKEN_SCHEME):
        raise TokenError(f"Not a HearthNet token (expected 'hntoken://v1/'): {text[:40]!r}")
    body = text[len(_TOKEN_SCHEME):]
    parts = body.split(".")
    if len(parts) != 3:
        raise TokenError("Token must have exactly 3 dot-separated parts")
    _header_b64, payload_b64, _sig_b64 = parts
    try:
        payload_bytes = _b64url_decode(payload_b64)
        pd = json.loads(payload_bytes)
    except Exception as exc:
        raise TokenError(f"Failed to decode token payload: {exc}") from exc

    required = {"iss", "sub", "aud", "iat", "exp", "nbf", "scope", "jti", "issued_via"}
    missing = required - pd.keys()
    if missing:
        raise TokenError(f"Token payload missing fields: {missing}")

    try:
        scope = _scope_from_dict(pd["scope"])
        return CapabilityToken(
            iss=pd["iss"],
            sub=pd["sub"],
            aud=pd["aud"],
            iat=int(pd["iat"]),
            exp=int(pd["exp"]),
            nbf=int(pd["nbf"]),
            scope=scope,
            jti=pd["jti"],
            issued_via=pd["issued_via"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise TokenError(f"Malformed token payload: {exc}") from exc


# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------


def verify_token(
    tok: CapabilityToken,
    community_manifest: Any | None = None,
    now: int | None = None,
) -> None:
    """Verify token validity (expiry, not-before). Raises TokenError on failure.

    If community_manifest is provided, the issuer is checked against membership.
    """
    ts = now if now is not None else int(time.time())
    if ts < tok.nbf:
        raise TokenError(f"Token not yet valid (nbf={tok.nbf}, now={ts})")
    if ts >= tok.exp:
        raise TokenError(f"Token expired (exp={tok.exp}, now={ts})")
    if not tok.iss.startswith("ed25519:"):
        raise TokenError(f"Issuer must be a full node_id: {tok.iss!r}")
    if not tok.jti:
        raise TokenError("Token has no jti")
    if community_manifest is not None:
        members = getattr(community_manifest, "members", None) or {}
        if isinstance(members, dict):
            member_ids = set(members.keys())
        elif isinstance(members, list):
            member_ids = set(members)
        else:
            member_ids = set()
        if member_ids and tok.iss not in member_ids:
            raise TokenError(f"Token issuer {tok.iss!r} is not a member of the community")
