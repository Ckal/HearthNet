"""FederationService — registers federation.* capabilities on the bus (M14)."""
from __future__ import annotations

from typing import Any

from hearthnet.federation.manifest import (
    FederationManifest,
    ManifestError,
    finalize_federation_manifest,
)
from hearthnet.federation.peering import (
    FederationStore,
    _proposal_from_dict,
)


class FederationService:
    """Manages bilateral community federation.

    Registers:
      federation.peer.list@1.0
      federation.peer.add@1.0
      federation.peer.remove@1.0
    """

    name = "federation"

    def __init__(
        self,
        keypair: Any,
        community_manifest: Any | None = None,
        store: FederationStore | None = None,
        bus: Any | None = None,
    ) -> None:
        self._kp = keypair
        self._community_manifest = community_manifest
        self._store = store or FederationStore()
        self._bus = bus

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, bus: Any) -> None:
        """Register all federation capabilities with the bus Registry."""
        from hearthnet.bus.capability import CapabilityDescriptor

        self._bus = bus
        registry = getattr(bus, "registry", None)
        if registry is None:
            return

        descriptors = [
            ("federation.peer.list", "1.0", self._handle_list),
            ("federation.peer.add", "1.0", self._handle_add),
            ("federation.peer.remove", "1.0", self._handle_remove),
        ]
        for name, version, handler in descriptors:
            desc = CapabilityDescriptor(
                name=name,
                version=version,
                stability="stable",
                params={},
                max_concurrent=2,
            )
            registry.register_local(desc, handler)

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _handle_list(self, params: dict) -> dict:
        """federation.peer.list@1.0 — list active federation peers.

        returns: {peers: list[{community_id, community_name, scope, expires_at}]}
        """
        manifests = self._store.list_active()
        our_community_id = getattr(self._community_manifest, "community_id", "")
        peers = []
        for m in manifests:
            # Determine which side we are to pick the correct scope
            if m.community_a_id == our_community_id:
                peer_id = m.community_b_id
                peer_name = m.community_b_name
                scope = m.scope_b_to_a  # scope they grant us
            else:
                peer_id = m.community_a_id
                peer_name = m.community_a_name
                scope = m.scope_a_to_b
            peers.append({
                "community_id": peer_id,
                "community_name": peer_name,
                "federation_id": m.federation_id,
                "scope": {
                    "capabilities": list(scope.capabilities),
                    "data_visibility": scope.data_visibility,
                },
                "expires_at": m.expires_at,
            })
        return {"peers": peers}

    def _handle_add(self, params: dict) -> dict:
        """federation.peer.add@1.0 — accept a signed proposal + co-sig and activate.

        params: {proposal_json: str, co_sig_json: str,
                 community_a_name?: str, community_b_name?: str}
        returns: {federation_id: str, active: bool}
        """
        import json as _json

        try:
            proposal_dict = _json.loads(params.get("proposal_json", "{}"))
            co_sig_dict = _json.loads(params.get("co_sig_json", "{}"))
        except Exception as exc:
            return {"error": f"JSON parse error: {exc}", "active": False, "federation_id": ""}

        try:
            proposal = _proposal_from_dict(proposal_dict)
            sig_a = proposal.proposer_sig
            sig_b = co_sig_dict.get("signature", "")
            community_a_name = params.get("community_a_name", "")
            community_b_name = params.get("community_b_name", "")
            manifest = finalize_federation_manifest(
                proposal,
                sig_a=sig_a,
                sig_b=sig_b,
                community_a_name=community_a_name,
                community_b_name=community_b_name,
            )
            self._store.add_manifest(manifest)
            return {"federation_id": manifest.federation_id, "active": True}
        except ManifestError as exc:
            return {"error": str(exc), "active": False, "federation_id": ""}

    def _handle_remove(self, params: dict) -> dict:
        """federation.peer.remove@1.0 — deactivate federation with a community.

        params: {community_id: str}
        returns: {removed: bool}
        """
        community_id = params.get("community_id", "")
        if not community_id:
            return {"removed": False, "error": "community_id required"}
        m = self._store.get_manifest(community_id)
        if m is None:
            return {"removed": False}
        self._store.remove(m.federation_id)
        return {"removed": True}

    # ------------------------------------------------------------------
    # Direct API
    # ------------------------------------------------------------------

    def add_manifest(self, manifest: FederationManifest) -> None:
        """Directly add a finalized manifest (bypasses the bus)."""
        self._store.add_manifest(manifest)

    def get_peer(self, community_id: str) -> FederationManifest | None:
        """Return the active manifest for a peer community, or None."""
        return self._store.get_manifest(community_id)

    def list_peers(self) -> list[FederationManifest]:
        """Return all active federation manifests."""
        return self._store.list_active()
