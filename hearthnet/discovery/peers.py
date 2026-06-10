"""M02 - Peer discovery: PeerRegistry.

Spec: docs/M02-discovery.md §3.1
Impl-ref: impl_ref.md §6

Holds PeerRecord entries discovered via mDNS or UDP multicast.
Async subscribe() notifies bus and UI on peer changes.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

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
    source: str = "memory"  # "mdns" | "udp" | "relay" | "memory"
    latency_ms: float = 0.0

    @property
    def node_id(self) -> str:
        """Short form: first 12 chars after 'ed25519:' or the full node_id if short."""
        return self.node_id_full

    def as_view(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id_full,
            "display_name": self.display_name,
            "community_id": self.community_id,
            "profile": self.profile,
            "last_seen": self.last_seen,
            "source": self.source,
        }


@dataclass(frozen=True)
class PeerEvent:
    kind: str  # "added" | "removed" | "updated"
    peer: PeerRecord


class PeerRegistry:
    """In-memory map of NodeID â†’ PeerRecord. Thread-safe via asyncio.Lock."""

    def __init__(self, our_node_id: str, community_id: str) -> None:
        self.our_node_id = our_node_id
        # Keep legacy attribute name for backward compatibility
        self.our_node_id_full = our_node_id
        self.community_id = community_id
        self._peers: dict[NodeID, PeerRecord] = {}
        self._lock = asyncio.Lock()
        self._subscribers: list[asyncio.Queue] = []
        self._pruning_aggressive = False
        self._pruning_task: asyncio.Task | None = None

    def upsert(self, record: PeerRecord) -> bool:
        """Add or update peer. Returns True if new peer was added."""
        existing = self._peers.get(record.node_id_full)
        self._peers[record.node_id_full] = record
        is_new = existing is None
        event_kind = "added" if is_new else "updated"
        self._notify(PeerEvent(kind=event_kind, peer=record))
        return is_new

    def remove(self, node_id: str) -> None:
        peer = self._peers.pop(node_id, None)
        if peer:
            self._notify(PeerEvent(kind="removed", peer=peer))

    def get(self, node_id: str) -> PeerRecord | None:
        return self._peers.get(node_id)

    def all(self) -> list[PeerRecord]:
        return list(self._peers.values())

    def count(self) -> int:
        return len(self._peers)

    def set_pruning_aggressive(self, aggressive: bool) -> None:
        self._pruning_aggressive = aggressive

    @property
    def prune_stale_seconds(self) -> int:
        from hearthnet.constants import PEER_PRUNE_AGGRESSIVE_SECONDS, PEER_PRUNE_NORMAL_SECONDS

        return PEER_PRUNE_AGGRESSIVE_SECONDS if self._pruning_aggressive else PEER_PRUNE_NORMAL_SECONDS

    def prune_stale(self, max_age_seconds: int | None = None) -> int:
        """Remove peers whose last_seen is beyond the prune threshold."""
        from hearthnet.constants import PEER_PRUNE_AGGRESSIVE_SECONDS, PEER_PRUNE_NORMAL_SECONDS
        if max_age_seconds is not None:
            threshold = max_age_seconds
        else:
            threshold = PEER_PRUNE_AGGRESSIVE_SECONDS if self._pruning_aggressive else PEER_PRUNE_NORMAL_SECONDS
        now = time.monotonic()
        stale = [nid for nid, peer in self._peers.items() if now - peer.last_seen > threshold]
        for nid in stale:
            self.remove(nid)
        return len(stale)

    async def start_pruner(self) -> None:
        self._pruning_task = asyncio.create_task(self._pruner_loop(), name="peer-pruner")

    async def _pruner_loop(self) -> None:
        while True:
            await asyncio.sleep(30)
            self.prune_stale()

    def subscribe(self) -> AsyncIterator[PeerEvent]:
        q: asyncio.Queue = asyncio.Queue(maxsize=50)
        self._subscribers.append(q)

        async def gen() -> AsyncIterator[PeerEvent]:
            try:
                while True:
                    event = await q.get()
                    yield event
            finally:
                self._subscribers.remove(q)

        return gen()

    def _notify(self, event: PeerEvent) -> None:
        for q in list(self._subscribers):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass

