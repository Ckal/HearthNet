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
from hearthnet.services.files import FileService
from hearthnet.services.moe import MoeService
from hearthnet.services.tools import PlantIdentificationService
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
        """FOR TESTS ONLY — install echo-LLM + in-memory services (no disk I/O, fast).

        Production code should call install_services() which auto-discovers real backends.
        """
        # Use demo- prefixed model name so LlmService creates _EchoBackend (test path)
        from hearthnet.services.demo import (
            LlmService as DemoLlm,
        )
        from hearthnet.services.demo import (
            MarketplaceService as DemoMarket,
        )
        from hearthnet.services.demo import (
            RagService as DemoRag,
        )

        model_name = "demo-remote" if internet_llm else "demo-local"
        services = [
            DemoLlm(model=model_name, requires_internet=internet_llm),
            DemoRag(
                corpus=corpus,
                documents=[
                    {
                        "id": "seed",
                        "title": "Water",
                        "text": "Store clean water and boil rainwater.",
                    }
                ],
            ),
            DemoMarket(),
            ChatService(self.node_id),
            FileService(),
            MoeService(bus=self.bus),
            PlantIdentificationService(bus=self.bus),
        ]
        # ModelDistributionService also needed in tests; use a temp BlobStore
        import tempfile
        from pathlib import Path

        from hearthnet.blobs.store import BlobStore
        from hearthnet.services.llm.model_distribution import ModelDistributionService

        tmp_store = BlobStore(Path(tempfile.mkdtemp()) / "blobs")
        services.append(
            ModelDistributionService(store=tmp_store, models_dir=None, bus=self.bus)
        )
        for service in services:
            self.bus.register_service(service)

    def install_services(
        self,
        *,
        corpus: str = "community",
        models_dir=None,
        blob_store=None,
    ) -> None:
        """Install real services with auto-discovered LLM backends.

        Backend discovery order (local-first, no internet unless explicitly enabled):
          1. OllamaBackend  — if ollama is running on localhost
          2. LlamaCppBackend — if llama.cpp HTTP server is running on localhost
          3. HfLocalBackend  — if transformers is installed (loads on first call)
          4. _UnavailableBackend — fallback: returns a clear error, not a silent echo

        Also installs ModelDistributionService so peers can pull model weights.
        """
        from hearthnet.services.llm.backends.hf_local import HfLocalBackend
        from hearthnet.services.llm.backends.ollama import OllamaBackend
        from hearthnet.services.llm.backends.openai_compat import OpenAICompatBackend
        from hearthnet.services.llm.model_distribution import ModelDistributionService

        backends = []
        ollama = OllamaBackend()
        if ollama.is_available():
            backends.append(ollama)

        # llama.cpp HTTP server on default port
        llama_http = OpenAICompatBackend(
            base_url="http://localhost:8080/v1",
            api_key_env="",
            model="local",
        )
        if llama_http.is_available():
            backends.append(llama_http)

        hf = HfLocalBackend()
        if hf.is_available():
            backends.append(hf)

        services = [
            LlmService(backends=backends or None),  # _UnavailableBackend if none found
            RagService(corpus=corpus),
            MarketplaceService(),
            ChatService(self.node_id),
            FileService(),
            MoeService(bus=self.bus),
            PlantIdentificationService(bus=self.bus),
        ]

        # Model weight distribution (BitTorrent-style M07/M26)
        # Use provided blob_store or auto-create a persistent one in ~/.hearthnet/blobs
        if blob_store is None:
            from pathlib import Path

            from hearthnet.blobs.store import BlobStore

            blob_store = BlobStore(Path.home() / ".hearthnet" / "blobs")

        model_svc = ModelDistributionService(
            store=blob_store,
            models_dir=models_dir,
            bus=self.bus,
        )
        services.append(model_svc)

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
