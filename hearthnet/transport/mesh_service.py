"""Mesh join service — redeem an invite/code into an all-to-all relay membership.

Exposes a single bus capability:

``mesh.join@1.0`` — given either a raw invite (``invite_text``) or an explicit
``relay_url`` (+ optional ``token``), join the relay hub so this node meshes
all-to-all with every other member over NAT. On success the roster peers are
already registered locally (by :class:`~hearthnet.transport.relay_client.RelayClient`),
so ``llm.chat`` / ``rag.query`` / ``chat.deliver`` route to them immediately.

This is the programmatic counterpart to the QR/redeem-code onboarding flow: the
invite already carries the relay endpoint (see
:func:`hearthnet.ui.onboarding.make_invite`), so a single ``mesh.join`` decodes
it and connects.
"""

from __future__ import annotations

from typing import Any

from hearthnet.bus.capability import CapabilityDescriptor, RouteRequest


class MeshService:
    name = "mesh"
    version = "1.0"

    def __init__(self, node: Any) -> None:
        self._node = node

    def capabilities(self) -> list[tuple[Any, ...]]:
        return [
            (
                CapabilityDescriptor(
                    name="mesh.join",
                    version=(1, 0),
                    trust_required="trusted",
                    idempotent=False,
                ),
                self.join,
            ),
        ]

    async def join(self, req: RouteRequest) -> dict[str, Any]:
        body = req.body.get("input", {}) or req.body.get("params", {})
        relay_url = body.get("relay_url")
        token = body.get("token") or body.get("relay_token")
        invite_text = body.get("invite_text") or body.get("invite")

        if invite_text and not relay_url:
            try:
                from hearthnet.ui.onboarding import decode_invite

                blob = decode_invite(str(invite_text))
            except Exception as exc:
                return {"error": "invite_invalid", "message": str(exc)}
            relay_url = blob.relay_url
            token = token or blob.relay_token
            if not relay_url:
                return {
                    "error": "no_relay",
                    "message": "invite does not carry a relay_url for mesh join",
                }

        if not relay_url:
            return {"error": "bad_request", "message": "relay_url or invite_text required"}

        try:
            result = await self._node.join_relay(str(relay_url), token=token or None)
        except Exception as exc:
            code = getattr(exc, "code", "relay_join_failed")
            return {"error": code, "message": str(exc)}

        roster = result.get("roster", [])
        return {
            "output": {
                "relay_url": relay_url,
                "joined": True,
                "members": [m.get("node_id") for m in roster],
                "member_count": len(roster),
            }
        }
