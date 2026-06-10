"""M12/Node - HearthNode composition root.

Spec: docs/M12-cli.md §5 (node.start 15-step sequence)
Impl-ref: impl_ref.md §17 (node.py, ManifestPublisher)

Wires all services together. The 15-step startup lives in node.start().
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from hearthnet.bus import CapabilityBus, InMemoryTransport
from hearthnet.discovery import PeerRecord, PeerRegistry
from hearthnet.emergency.detector import Detector
from hearthnet.emergency.state import StateBus
from hearthnet.facades import ChatFacade, MarketplaceFacade, RagFacade
from hearthnet.services import ChatService, LlmService, MarketplaceService, RagService
from hearthnet.types import CommunityID, Endpoint, NodeID, Profile


@dataclass
class NodeManifest:
    node_id: NodeID
    display_name: str
    community_id: CommunityID
    profile: Profile
    capabilities: list[dict[str, Any]]

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": 1,
            "contract_version": "1.0",
            "node_id": self.node_id,
            "display_name": self.display_name,
            "community_id": self.community_id,
            "profile": self.profile,
            "capabilities": self.capabilities,
        }


class HearthNode:
    def __init__(
        self,
        node_id: NodeID,
        display_name: str,
        community_id: CommunityID,
        *,
        transport: InMemoryTransport | None = None,
        profile: Profile = "hearth",
    ) -> None:
        self.node_id = node_id
        self.display_name = display_name
        self.community_id = community_id
        self.profile: Profile = profile
        self.bus = CapabilityBus(node_id, community_id, transport)
        self.peers = PeerRegistry(node_id, community_id)
        self.state_bus = StateBus()
        self.detector = Detector(self.bus, self.state_bus, self.peers)
        self.rag = RagFacade(self.bus)
        self.chat = ChatFacade(self.bus)
        self.marketplace = MarketplaceFacade(self.bus)

    def install_demo_services(self, *, internet_llm: bool = False, corpus: str = "demo") -> None:
        services = [
            LlmService(
                model="demo-remote" if internet_llm else "demo-local",
                requires_internet=internet_llm,
            ),
            RagService(
                corpus=corpus,
                documents=[
                    {
                        "id": "seed",
                        "title": "Water",
                        "text": "Store clean water and boil rainwater.",
                    }
                ],
            ),
            MarketplaceService(),
            ChatService(self.node_id),
        ]
        for service in services:
            self.bus.register_service(service)

    def manifest(self) -> NodeManifest:
        capabilities = [
            {
                "name": entry.descriptor.name,
                "version": entry.descriptor.version_str,
                "stability": entry.descriptor.stability,
                "schema_hash": entry.descriptor.schema_hash(),
                "params": dict(entry.descriptor.params),
                "max_concurrent": entry.descriptor.max_concurrent,
            }
            for entry in self.bus.registry.all_local()
        ]
        return NodeManifest(
            self.node_id, self.display_name, self.community_id, self.profile, capabilities
        )

    def discover(self, other: HearthNode) -> None:
        record = PeerRecord(
            node_id_full=other.node_id,
            display_name=other.display_name,
            community_id=other.community_id,
            profile=other.profile,
            endpoints=[Endpoint("memory", other.node_id, 0)],
            manifest=other.manifest().as_dict(),
            last_seen=time.monotonic(),
        )
        if self.peers.upsert(record):
            self.bus.registry.update_from_peer_manifest(record, record.manifest or {})

    def snapshot(self) -> dict[str, Any]:
        topology = self.bus.topology_snapshot([peer.as_view() for peer in self.peers.all()])
        return {
            "node": {
                "node_id": self.node_id,
                "display_name": self.display_name,
                "community_id": self.community_id,
                "profile": self.profile,
            },
            "emergency": self.state_bus.current(),
            "topology": topology,
        }


class InMemoryNetwork:
    def __init__(self) -> None:
        self.transport = InMemoryTransport()
        self.nodes: list[HearthNode] = []

    def add_node(
        self, node_id: NodeID, display_name: str, community_id: CommunityID = "ed25519:community"
    ) -> HearthNode:
        node = HearthNode(node_id, display_name, community_id, transport=self.transport)
        self.nodes.append(node)
        return node

    def mesh_discover(self) -> None:
        for node in self.nodes:
            for other in self.nodes:
                if node is not other:
                    node.discover(other)

