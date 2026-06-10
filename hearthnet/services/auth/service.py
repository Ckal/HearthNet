"""AuthService — registers auth.token.* capabilities on the bus (M16)."""

from __future__ import annotations

from typing import Any

from hearthnet.identity.tokens import (
    CapabilityToken,
    TokenError,
    TokenScope,
    decode_token,
    issue_token,
    verify_token,
)


class AuthService:
    """Manages capability token issuance, verification, and revocation.

    Registers:
      auth.token.issue@1.0
      auth.token.verify@1.0
      auth.token.revoke@1.0
    """

    name = "auth"

    def __init__(
        self,
        keypair: Any,
        community_manifest: Any | None = None,
        bus: Any | None = None,
    ) -> None:
        self._kp = keypair
        self._community_manifest = community_manifest
        self._bus = bus
        self._revoked_jtis: set[str] = set()

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, bus: Any) -> None:
        """Register all auth capabilities with the bus Registry."""
        from hearthnet.bus.capability import CapabilityDescriptor

        self._bus = bus
        registry = getattr(bus, "registry", None)
        if registry is None:
            return

        descriptors = [
            ("auth.token.issue", "1.0", self._handle_issue),
            ("auth.token.verify", "1.0", self._handle_verify),
            ("auth.token.revoke", "1.0", self._handle_revoke),
        ]
        for name, version_str, handler in descriptors:
            major, minor = map(int, version_str.split("."))
            desc = CapabilityDescriptor(
                name=name,
                version=(major, minor),
                stability="stable",
                params={},
                max_concurrent=4,
            )
            registry.register_local(desc, handler)

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _handle_issue(self, params: dict) -> dict:
        """auth.token.issue@1.0 handler.

        params: {subject, audience, capabilities: list[str],
                 ttl_seconds=3600, issued_via="manual",
                 max_uses=None, max_calls_total=None}
        returns: {token: str, expires_at: int}
        """
        subject = params.get("subject", "")
        audience = params.get("audience", "")
        capabilities = list(params.get("capabilities", []))
        ttl = int(params.get("ttl_seconds", 3600))
        issued_via = str(params.get("issued_via", "manual"))
        max_uses = params.get("max_uses")
        max_calls_total = params.get("max_calls_total")

        scope = TokenScope(
            capabilities=capabilities,
            max_uses=max_uses,
            max_calls_total=max_calls_total,
        )
        try:
            tok, encoded = issue_token(
                self._kp,
                subject_node_id=subject,
                audience=audience,
                scope=scope,
                ttl_seconds=ttl,
                issued_via=issued_via,
            )
        except TokenError as exc:
            return {"error": str(exc)}

        return {"token": encoded, "expires_at": tok.exp}

    def _handle_verify(self, params: dict) -> dict:
        """auth.token.verify@1.0 handler.

        params: {token: str}
        returns: {valid: bool, subject: str | None, capabilities: list[str], expires_at: int}
        """
        text = params.get("token", "")
        try:
            tok = decode_token(text)
        except TokenError as exc:
            return {
                "valid": False,
                "subject": None,
                "capabilities": [],
                "expires_at": 0,
                "error": str(exc),
            }

        # Check revocation
        if tok.jti in self._revoked_jtis:
            return {
                "valid": False,
                "subject": tok.sub,
                "capabilities": list(tok.scope.capabilities),
                "expires_at": tok.exp,
                "error": "Token has been revoked",
            }

        try:
            verify_token(tok, community_manifest=self._community_manifest)
        except TokenError as exc:
            return {
                "valid": False,
                "subject": tok.sub,
                "capabilities": list(tok.scope.capabilities),
                "expires_at": tok.exp,
                "error": str(exc),
            }

        return {
            "valid": True,
            "subject": tok.sub,
            "capabilities": list(tok.scope.capabilities),
            "expires_at": tok.exp,
        }

    def _handle_revoke(self, params: dict) -> dict:
        """auth.token.revoke@1.0 handler.

        params: {jti: str}
        returns: {revoked: bool}
        """
        jti = params.get("jti", "")
        if not jti:
            return {"revoked": False, "error": "No jti provided"}
        self._revoked_jtis.add(jti)
        return {"revoked": True}

    # ------------------------------------------------------------------
    # Direct API (for use without the bus)
    # ------------------------------------------------------------------

    def issue(
        self,
        subject: str,
        audience: str,
        capabilities: list[str],
        ttl_seconds: int = 3600,
        issued_via: str = "manual",
    ) -> tuple[CapabilityToken, str]:
        """Issue a token directly (bypasses the bus)."""
        scope = TokenScope(capabilities=capabilities)
        return issue_token(
            self._kp,
            subject_node_id=subject,
            audience=audience,
            scope=scope,
            ttl_seconds=ttl_seconds,
            issued_via=issued_via,
        )

    def verify(self, text: str) -> CapabilityToken:
        """Verify a token string directly. Raises TokenError if invalid."""
        tok = decode_token(text)
        if tok.jti in self._revoked_jtis:
            raise TokenError(f"Token {tok.jti!r} has been revoked")
        verify_token(tok, community_manifest=self._community_manifest)
        return tok

    def revoke(self, jti: str) -> None:
        """Revoke a token by JTI (in-memory, not persisted across restart)."""
        self._revoked_jtis.add(jti)
