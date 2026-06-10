"""M22 — Mobile invite helpers.

Generates mobile-targeted invite deep links (``hnapp://``) and QR codes
for the mobile native client (Flutter).  Builds on top of the Phase 1
onboarding module (M13).
"""

from __future__ import annotations

import base64
import hashlib
import json
import time
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Invite blob for mobile clients
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MobileInviteBlob:
    """Compact invite that the mobile app can parse from a QR or deep link.

    Wire format: ``hnapp://v1/<b64url(json_payload)>``
    The payload is JSON with fields defined below.
    """

    community_id: str
    community_name: str
    anchor_endpoints: list[str]
    """HTTP(S) or WebSocket URLs of community anchors the app can reach."""

    invited_by: str
    """node_id of the inviting user (display hint only)."""

    relay_url: str | None = None
    """Optional relay tier URL for NAT-traversal push delivery (M15)."""

    invite_token: str | None = None
    """One-time capability token the app exchanges on first contact (M16)."""

    created_at: float = field(default_factory=time.time)
    expires_at: float | None = None

    def is_expired(self, now: float | None = None) -> bool:
        t = now if now is not None else time.time()
        return self.expires_at is not None and t > self.expires_at

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "v": 1,
            "community_id": self.community_id,
            "community_name": self.community_name,
            "anchor_endpoints": self.anchor_endpoints,
            "invited_by": self.invited_by,
            "relay_url": self.relay_url,
            "invite_token": self.invite_token,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
        }

    def to_deep_link(self) -> str:
        """Encode as ``hnapp://v1/<b64url>``."""
        payload = json.dumps(self.to_dict(), separators=(",", ":"), sort_keys=True)
        b64 = base64.urlsafe_b64encode(payload.encode()).rstrip(b"=").decode()
        return f"hnapp://v1/{b64}"

    def fingerprint(self) -> str:
        """SHA-256 (hex, 16 chars) of the JSON payload for logging."""
        raw = json.dumps(self.to_dict(), separators=(",", ":"), sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    @classmethod
    def from_deep_link(cls, deep_link: str) -> MobileInviteBlob:
        """Parse a deep link produced by :meth:`to_deep_link`."""
        if not deep_link.startswith("hnapp://v1/"):
            raise ValueError(f"Not a valid hnapp:// deep link: {deep_link!r}")
        b64 = deep_link[len("hnapp://v1/") :]
        # Re-add padding
        padding = 4 - len(b64) % 4
        if padding != 4:
            b64 += "=" * padding
        payload = json.loads(base64.urlsafe_b64decode(b64).decode())
        return cls(
            community_id=payload["community_id"],
            community_name=payload["community_name"],
            anchor_endpoints=payload["anchor_endpoints"],
            invited_by=payload["invited_by"],
            relay_url=payload.get("relay_url"),
            invite_token=payload.get("invite_token"),
            created_at=payload.get("created_at", time.time()),
            expires_at=payload.get("expires_at"),
        )


# ---------------------------------------------------------------------------
# QR code rendering (qrcode optional)
# ---------------------------------------------------------------------------


def render_qr_svg(blob: MobileInviteBlob) -> str | None:
    """Return an SVG string for the invite QR code, or None if ``qrcode`` is
    not installed.  The SVG can be embedded directly in HTML."""
    try:
        import qrcode  # type: ignore
        import qrcode.image.svg  # type: ignore

        factory = qrcode.image.svg.SvgPathImage
        qr = qrcode.make(blob.to_deep_link(), image_factory=factory)
        import io

        buf = io.BytesIO()
        qr.save(buf)
        return buf.getvalue().decode("utf-8")
    except ImportError:
        return None


def render_qr_terminal(blob: MobileInviteBlob) -> str:
    """Return the QR code as ASCII art (uses ``qrcode`` if available, else
    falls back to the raw deep link)."""
    try:
        import qrcode  # type: ignore

        qr = qrcode.QRCode()
        qr.add_data(blob.to_deep_link())
        qr.make(fit=True)
        import io

        buf = io.StringIO()
        qr.print_ascii(out=buf)
        return buf.getvalue()
    except ImportError:
        return blob.to_deep_link()


# ---------------------------------------------------------------------------
# Factory helper
# ---------------------------------------------------------------------------


def build_mobile_invite(
    community_id: str,
    community_name: str,
    anchor_endpoints: list[str],
    invited_by: str,
    relay_url: str | None = None,
    invite_token: str | None = None,
    ttl_seconds: float = 86_400 * 7,  # 7 days default
) -> MobileInviteBlob:
    """Create a :class:`MobileInviteBlob` with a default 7-day TTL."""
    now = time.time()
    return MobileInviteBlob(
        community_id=community_id,
        community_name=community_name,
        anchor_endpoints=anchor_endpoints,
        invited_by=invited_by,
        relay_url=relay_url,
        invite_token=invite_token,
        created_at=now,
        expires_at=now + ttl_seconds,
    )
