from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from hearthnet.types import CommunityID, Endpoint, NodeID, Profile


@dataclass
class PeerRecord:
    node_id_full: NodeID
    display_name: str
    community_id: CommunityID
    profile: Profile = "hearth"
    endpoints: list[Endpoint] = field(default_factory=list)
    manifest: dict[str, Any] | None = None
    last_seen: float = field(default_factory=time.monotonic)
    rtt_ms: float | None = None
    source: str = "simulated"

    @property
    def node_id(self) -> str:
        return self.node_id_full.split(":", 1)[-1][:12]

    def as_view(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id_full,
            "display_name": self.display_name,
            "community_id": self.community_id,
            "profile": self.profile,
            "capabilities": [cap["name"] for cap in (self.manifest or {}).get("capabilities", [])],
            "source": self.source,
            "rtt_ms": self.rtt_ms,
        }


class PeerRegistry:
    def __init__(self, our_node_id_full: NodeID, community_id: CommunityID) -> None:
        self.our_node_id_full = our_node_id_full
        self.community_id = community_id
        self._peers: dict[NodeID, PeerRecord] = {}
        self.prune_stale_seconds = 90

    def upsert(self, record: PeerRecord) -> bool:
        if record.node_id_full == self.our_node_id_full or record.community_id != self.community_id:
            return False
        is_new = record.node_id_full not in self._peers
        record.last_seen = time.monotonic()
        self._peers[record.node_id_full] = record
        return is_new

    def remove(self, node_id_full: NodeID) -> bool:
        return self._peers.pop(node_id_full, None) is not None

    def get(self, node_id_full: NodeID) -> PeerRecord | None:
        return self._peers.get(node_id_full)

    def all(self) -> list[PeerRecord]:
        return list(self._peers.values())

    def prune_stale(self, max_age_seconds: int | None = None) -> int:
        max_age = max_age_seconds if max_age_seconds is not None else self.prune_stale_seconds
        cutoff = time.monotonic() - max_age
        stale = [node_id for node_id, peer in self._peers.items() if peer.last_seen < cutoff]
        for node_id in stale:
            self._peers.pop(node_id, None)
        return len(stale)

    def set_pruning_aggressive(self, enabled: bool) -> None:
        self.prune_stale_seconds = 30 if enabled else 90
