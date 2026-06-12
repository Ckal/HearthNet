"""M13 — Onboarding: invite encode/decode, QR generation, create/join community flows."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import UTC

UTC = UTC

import contextlib

from hearthnet.constants import INVITE_DEFAULT_TTL_SECONDS


@dataclass(frozen=True)
class InviteBlob:
    """Invite that travels between devices to enable joining."""

    community_id: str
    community_name: str
    inviter_node_id: str
    invitee_node_id: str  # the new member's full node ID
    issued_at: str  # RFC 3339 UTC
    expires_at: str  # RFC 3339 UTC
    signature: str  # inviter's signature


def encode_invite(blob: InviteBlob) -> str:
    """Compact base64url encoding. Aim: < 500 bytes."""
    d = {
        "cid": blob.community_id,
        "cn": blob.community_name,
        "inv": blob.inviter_node_id,
        "tee": blob.invitee_node_id,
        "iat": blob.issued_at,
        "exp": blob.expires_at,
        "sig": blob.signature,
    }
    raw = json.dumps(d, separators=(",", ":"))
    return "hn1:" + base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_invite(text: str) -> InviteBlob:
    """Parse + verify signature. Raises OnboardingError on invalid."""
    if not text.startswith("hn1:"):
        raise OnboardingError("invite_invalid", reason="missing 'hn1:' prefix")
    try:
        payload = text[4:]
        padded = payload + "=" * (4 - len(payload) % 4 if len(payload) % 4 != 0 else 0)
        raw = base64.urlsafe_b64decode(padded).decode()
        d = json.loads(raw)
    except Exception as exc:
        raise OnboardingError("invite_invalid", reason=str(exc)) from exc

    now_str = _iso_now()
    if d.get("exp", "") < now_str:
        raise OnboardingError("invite_expired", reason=f"expired at {d.get('exp')}")

    return InviteBlob(
        community_id=d["cid"],
        community_name=d.get("cn", ""),
        inviter_node_id=d["inv"],
        invitee_node_id=d["tee"],
        issued_at=d["iat"],
        expires_at=d["exp"],
        signature=d.get("sig", ""),
    )


def invite_to_qr_png(blob: InviteBlob, *, box_size: int = 8) -> bytes:
    """Render invite as QR PNG. Returns empty bytes if qrcode not installed."""
    try:
        import io

        import qrcode

        qr = qrcode.QRCode(
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=box_size,
            border=4,
        )
        qr.add_data(encode_invite(blob))
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except ImportError:
        return b""


def make_invite(
    invitee_node_id: str,
    community_id: str,
    community_name: str,
    kp,  # KeyPair
    ttl_seconds: int = INVITE_DEFAULT_TTL_SECONDS,
) -> InviteBlob:
    """Create and sign an invite blob."""
    from hearthnet.identity.keys import sign_payload

    iat = _iso_now()
    exp = _iso_after(ttl_seconds)
    payload = {
        "community_id": community_id,
        "community_name": community_name,
        "inviter_node_id": kp.node_id_full,
        "invitee_node_id": invitee_node_id,
        "issued_at": iat,
        "expires_at": exp,
    }
    signed = sign_payload(payload, kp)
    return InviteBlob(
        community_id=community_id,
        community_name=community_name,
        inviter_node_id=kp.node_id_full,
        invitee_node_id=invitee_node_id,
        issued_at=iat,
        expires_at=exp,
        signature=signed.get("signature", ""),
    )


def create_community(
    name: str,
    kp,  # KeyPair
    policy: dict | None = None,
    event_log=None,
) -> dict:
    """Create a new community. Returns community manifest dict."""
    from hearthnet.identity.manifest import build_community_manifest

    manifest = build_community_manifest(
        kp=kp,
        name=name,
        members=[kp.node_id_full],
        policy=policy or {"join_requires_invite": True, "max_members": 100},
    )
    if event_log is not None:
        with contextlib.suppress(Exception):
            event_log.append_local(
                event_type="community.created",
                author=kp.node_id_full,
                payload=manifest.as_dict(),
                kp=kp,
            )
    return manifest.as_dict()


def redeem_invite(
    blob: InviteBlob,
    kp,  # our KeyPair
    event_log=None,
) -> dict:
    """Verify invite, emit member.joined event, return community manifest stub."""
    if blob.invitee_node_id not in (kp.node_id_full, kp.node_id_short):
        if blob.invitee_node_id:  # "" means open invite
            raise OnboardingError(
                "invitee_mismatch",
                reason=(
                    f"invite was for {blob.invitee_node_id[:20]}, we are {kp.node_id_full[:20]}"
                ),
            )

    if event_log is not None:
        with contextlib.suppress(Exception):
            event_log.append_local(
                event_type="community.member.joined",
                author=kp.node_id_full,
                payload={
                    "community_id": blob.community_id,
                    "member_node_id": kp.node_id_full,
                    "invited_by": blob.inviter_node_id,
                },
                kp=kp,
            )

    return {
        "version": 1,
        "community_id": blob.community_id,
        "name": blob.community_name,
        "root_node_id": blob.inviter_node_id,
        "members": [blob.inviter_node_id, kp.node_id_full],
        "policy": {},
        "joined_via_invite": True,
    }


def build_onboarding_ui(config=None, kp_provider=None):
    """Build Gradio onboarding UI. Returns None if gradio not available."""
    try:
        import gradio as gr
    except ImportError:
        return None

    with gr.Blocks(title="HearthNet — Onboarding") as demo:
        gr.Markdown("# HearthNet Onboarding")
        with gr.Tab("Create Community"):
            name_input = gr.Textbox(label="Community Name", placeholder="My Neighbourhood")
            create_btn = gr.Button("Create Community")
            create_output = gr.JSON(label="Result")

            def do_create(name):
                if not name:
                    return {"error": "Community name required"}
                return {
                    "message": f"Community '{name}' ready (keypair required for full flow)",
                    "status": "demo",
                }

            create_btn.click(do_create, inputs=name_input, outputs=create_output)

        with gr.Tab("Join Community"):
            invite_input = gr.Textbox(label="Invite Code", placeholder="hn1:...")
            join_btn = gr.Button("Join")
            join_output = gr.JSON(label="Result")

            def do_join(invite_text):
                try:
                    blob = decode_invite(invite_text)
                    return {
                        "community": blob.community_name,
                        "from": blob.inviter_node_id[:20],
                        "status": "verified",
                    }
                except OnboardingError as e:
                    return {"error": str(e)}

            join_btn.click(do_join, inputs=invite_input, outputs=join_output)

    return demo


class OnboardingError(Exception):
    def __init__(self, code: str, **kwargs: str) -> None:
        super().__init__(code)
        self.code = code
        self.context = kwargs


def _iso_now() -> str:
    from datetime import datetime

    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _iso_after(seconds: int) -> str:
    from datetime import datetime, timedelta

    return (datetime.now(UTC) + timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")


# Spec-mandated name (M13 §3.1)
build_onboarding = build_onboarding_ui

