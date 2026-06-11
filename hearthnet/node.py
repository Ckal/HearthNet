"""M12/Node - HearthNode composition root.

Spec: docs/M12-cli.md Â§5 (node.start 15-step sequence)
Impl-ref: impl_ref.md Â§17 (node.py, ManifestPublisher)

Wires all services together. The 15-step startup lives in node.start().
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
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

_log = logging.getLogger(__name__)

# Gossip-sync period in seconds
_GOSSIP_INTERVAL_SECONDS = 30


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

        # Populated by start()
        self._http_server: Any = None
        self._event_log: Any = None
        self._replay_engine: Any = None
        self._mdns_announcer: Any = None
        self._mdns_browser: Any = None
        self._udp_announcer: Any = None
        self._udp_listener: Any = None
        self._gossip_task: asyncio.Task | None = None
        self._emergency_task: asyncio.Task | None = None
        self._pubsub_task: asyncio.Task | None = None
        self._started: bool = False

    # ------------------------------------------------------------------
    # Service installation
    # ------------------------------------------------------------------

    def install_demo_services(self, *, internet_llm: bool = False, corpus: str = "demo") -> None:
        """FOR TESTS ONLY â€” install echo-LLM + in-memory services (no disk I/O, fast).

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

        from hearthnet.blobs.store import BlobStore
        from hearthnet.services.llm.model_distribution import ModelDistributionService
        from hearthnet.services.protocol import ProtocolService

        tmp_store = BlobStore(Path(tempfile.mkdtemp()) / "blobs")
        services.append(
            ModelDistributionService(store=tmp_store, models_dir=None, bus=self.bus)
        )
        services.append(ProtocolService(node=self))
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
          1. OllamaBackend  â€” if ollama is running on localhost
          2. LlamaCppBackend â€” if llama.cpp HTTP server is running on localhost
          3. HfLocalBackend  â€” if transformers is installed (loads on first call)
          4. _UnavailableBackend â€” fallback: returns a clear error, not a silent echo

        Also installs ModelDistributionService so peers can pull model weights.
        """
        import os

        from hearthnet.services.llm.backends.hf_local import HfLocalBackend
        from hearthnet.services.llm.backends.modal_backend import ModalBackend
        from hearthnet.services.llm.backends.nemotron import NemotronBackend
        from hearthnet.services.llm.backends.ollama import OllamaBackend
        from hearthnet.services.llm.backends.openai_compat import OpenAICompatBackend
        from hearthnet.services.llm.backends.openbmb import OpenBmbBackend
        from hearthnet.services.llm.model_distribution import ModelDistributionService
        from hearthnet.services.protocol import ProtocolService

        backends = []

        # 1. Ollama (best quality, zero-config local)
        ollama = OllamaBackend()
        if ollama.is_available():
            backends.append(ollama)

        # 2. llama.cpp HTTP server on default port
        llama_http = OpenAICompatBackend(
            base_url="http://localhost:8080/v1",
            api_key_env="",
            model="local",
        )
        if llama_http.is_available():
            backends.append(llama_http)

        # 3. MiniCPM local server (OpenBMB prize track)
        if os.getenv("MINICPM_URL"):
            minicpm = OpenBmbBackend(base_url=os.getenv("MINICPM_URL", "http://localhost:8000"))
            if minicpm.is_available():
                backends.append(minicpm)
                _log.info("MiniCPM backend registered from MINICPM_URL")

        # 4. NVIDIA Nemotron (cloud NIM or local; NVIDIA prize track)
        if os.getenv("NVIDIA_API_KEY"):
            nemotron = NemotronBackend(api_key_env="NVIDIA_API_KEY")
            backends.append(nemotron)  # cloud — no local check needed
            _log.info("Nemotron backend registered (NVIDIA_API_KEY set)")
        elif os.getenv("NEMOTRON_URL"):
            nemotron_local = NemotronBackend(
                base_url=os.getenv("NEMOTRON_URL", "http://localhost:8001"),
                local=True,
            )
            if nemotron_local.is_available():
                backends.append(nemotron_local)
                _log.info("Nemotron local backend registered from NEMOTRON_URL")

        # 5. Modal serverless GPU (Modal prize track)
        if os.getenv("MODAL_ENDPOINT"):
            modal_b = ModalBackend()
            if modal_b.is_available():
                backends.append(modal_b)
                _log.info("Modal backend registered from MODAL_ENDPOINT")

        # 6. HF Transformers local (always available if transformers installed)
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
            ProtocolService(node=self),
        ]

        # Model weight distribution (BitTorrent-style M07/M26)
        # Use provided blob_store or auto-create a persistent one in ~/.hearthnet/blobs
        if blob_store is None:
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

    # ------------------------------------------------------------------
    # 15-step startup / shutdown
    # ------------------------------------------------------------------

    async def start(
        self,
        *,
        host: str = "0.0.0.0",  # nosec B104
        port: int = 7080,
        data_dir: Path | str | None = None,
        gossip_interval: int = _GOSSIP_INTERVAL_SECONDS,
    ) -> None:
        """Start the node â€” wires all subsystems.

        Steps:
         1-2. Already done: node_id + bus created in __init__
           3. Start mDNS + UDP peer discovery
           4. Load config (external; this method receives data_dir)
           5. Services already registered by caller via install_services()
           6. (LLM warmup deferred to first call)
           7. (RAG warmup deferred to first call)
           8. Start Detector (emergency probe loop)
           9. Start EventLog + ReplayEngine
          10. Start FastAPI HttpServer (X01)
          11. Publish manifest (mDNS)
          12. (Community join via invite; deferred to CLI/UI)
          13. Start observability
          14. (Federation; deferred)
          15. Signal ready
        """
        if self._started:
            return

        _log.info("HearthNode.start() node_id=%s port=%d", self.node_id, port)
        data_dir_path = (
            Path(data_dir)
            if data_dir
            else Path.home() / ".hearthnet" / "nodes" / self.node_id[:16]
        )
        data_dir_path.mkdir(parents=True, exist_ok=True)

        # â”€â”€ Step 9: Event log + replay engine â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        try:
            from hearthnet.events import EventLog, ReplayEngine

            self._event_log = EventLog(
                data_dir_path / "events.db", self.community_id, self.node_id
            )
            self._replay_engine = ReplayEngine(self._event_log)
            _log.debug("EventLog opened at %s", data_dir_path / "events.db")
        except Exception as exc:
            _log.warning("EventLog init failed (non-fatal): %s", exc)

        # â”€â”€ Step 3: Peer discovery (mDNS + UDP) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        caps = [e.descriptor.name for e in self.bus.registry.all_local()]
        try:
            from hearthnet.discovery.mdns import MdnsAnnouncer, MdnsBrowser
            from hearthnet.discovery.udp import UdpAnnouncer, UdpListener

            self._mdns_announcer = MdnsAnnouncer(
                self.peers,
                self.node_id,
                self.display_name,
                port=port,
                properties={"profile": self.profile, "caps": caps},
            )
            self._mdns_browser = MdnsBrowser(self.peers, self.community_id)
            self._udp_announcer = UdpAnnouncer(
                self.peers, self.node_id, self.community_id, port=port, caps=caps
            )
            self._udp_listener = UdpListener(self.peers, self.community_id)

            await self._mdns_announcer.start()
            await self._mdns_browser.start()
            await self._udp_announcer.start()
            await self._udp_listener.start()
            _log.debug("mDNS + UDP discovery started on port %d", port)
        except Exception as exc:
            _log.warning("Discovery init failed (non-fatal): %s", exc)

        # â”€â”€ Step 8: Emergency detector â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        try:
            self._emergency_task = asyncio.create_task(
                self.detector.run(), name="emergency-detector"
            )
        except Exception as exc:
            _log.warning("Emergency detector start failed (non-fatal): %s", exc)

        # â”€â”€ Step 10: HTTP server (X01) + WebSocket pubsub (X06) â”€â”€â”€â”€â”€â”€â”€
        try:
            from hearthnet.events.sync import SyncServer
            from hearthnet.transport.server import HttpServer

            sync_server = SyncServer(self._event_log) if self._event_log else None
            self._http_server = HttpServer(
                bus=self.bus,
                node_manifest_fn=lambda: self.manifest().as_dict(),
                sync_server=sync_server,
                host=host,
                port=port,
            )
            self._http_server.build_app()
            await self._http_server.start()
            _log.info("HTTP server listening on %s:%d", host, port)

            # Wire StateBus â†’ WebSocket pubsub (X06)
            if self._http_server._ws_pubsub is not None:
                self._pubsub_task = asyncio.create_task(
                    self._state_bus_to_pubsub(), name="state-pubsub"
                )
        except Exception as exc:
            _log.warning("HTTP server start failed (non-fatal): %s", exc)

        # â”€â”€ Gossip sync loop (X02) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        if self._event_log is not None:
            self._gossip_task = asyncio.create_task(
                self._gossip_loop(gossip_interval), name="gossip-sync"
            )

        self._started = True
        _log.info("HearthNode ready: %s", self.node_id)

    async def stop(self) -> None:
        """Gracefully stop all background tasks and subsystems."""
        if not self._started:
            return

        _log.info("HearthNode.stop() node_id=%s", self.node_id)
        self._started = False

        # Close event log
        if self._event_log is not None:
            try:
                self._event_log.close()
            except Exception:
                pass
            self._event_log = None

        # Stop emergency detector
        try:
            await self.detector.stop()
        except Exception:
            pass

        # Cancel background tasks
        for task_attr in ("_gossip_task", "_pubsub_task"):
            task = getattr(self, task_attr, None)
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
            setattr(self, task_attr, None)

        # Stop discovery
        for attr in ("_udp_announcer", "_udp_listener", "_mdns_announcer"):
            obj = getattr(self, attr, None)
            if obj:
                try:
                    await obj.stop()
                except Exception:
                    pass
        if self._mdns_browser:
            try:
                if hasattr(self._mdns_browser, "stop"):
                    await self._mdns_browser.stop()
            except Exception:
                pass

        # Stop HTTP server
        if self._http_server:
            try:
                await self._http_server.shutdown()
            except Exception:
                pass
            self._http_server = None

    # ------------------------------------------------------------------
    # Background tasks
    # ------------------------------------------------------------------

    async def _gossip_loop(self, interval: int) -> None:
        """Periodically sync event log with all known peers (X02 gossip)."""
        from hearthnet.events.sync import SyncClient
        from hearthnet.transport.client import HttpClient

        http_client = HttpClient(self.node_id, self.community_id)
        sync_client = SyncClient(self._event_log, http_client)

        while True:
            await asyncio.sleep(interval)
            for peer in self.peers.all():
                if not peer.endpoints:
                    continue
                ep = peer.endpoints[0]
                if ep.transport == "memory":
                    continue  # in-process; no HTTP needed
                peer_url = f"http://{ep.host}:{ep.port}"
                try:
                    result = await sync_client.sync_with(peer_url, self.community_id)
                    if result.received_count or result.sent_count:
                        _log.debug(
                            "Gossip with %s: sent=%d recv=%d ms=%d",
                            peer.display_name,
                            result.sent_count,
                            result.received_count,
                            result.duration_ms,
                        )
                except Exception as exc:
                    _log.debug("Gossip sync with %s failed: %s", peer.display_name, exc)

    async def _state_bus_to_pubsub(self) -> None:
        """Forward StateBus state changes to the WebSocket pubsub (X06)."""
        try:
            async for state in self.state_bus.subscribe():
                if self._http_server is None:
                    break
                await self._http_server.publish_event(
                    topic="emergency.mode.changed",
                    event="emergency.mode.changed",
                    data={
                        "mode": state.mode,
                        "mode_label": state.mode_label,
                        "changed_at": state.changed_at,
                        "probe_results": state.probe_results,
                        "consecutive_fails": state.consecutive_fails,
                    },
                )
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            _log.warning("state_bus_to_pubsub error: %s", exc)

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

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
            "started": self._started,
            "event_log_head": self._event_log.head() if self._event_log else None,
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


# ---------------------------------------------------------------------------
# PeriodicTask — generic async interval runner (M12 §5)
# ---------------------------------------------------------------------------


class PeriodicTask:
    """Run *fn* every *interval_seconds* until cancelled.

    Usage::

        task = PeriodicTask(my_async_fn, interval_seconds=60)
        asyncio.create_task(task.run())
    """

    def __init__(self, fn, interval_seconds: int) -> None:
        self._fn = fn
        self._interval = interval_seconds

    async def run(self) -> None:
        while True:
            await asyncio.sleep(self._interval)
            try:
                await self._fn()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                _log.debug("PeriodicTask %s error: %s", self._fn, exc)


# ---------------------------------------------------------------------------
# ManifestPublisher — republishes node manifest to mDNS + UDP (M12 §5)
# ---------------------------------------------------------------------------

_MANIFEST_REPUBLISH_INTERVAL_SECONDS = 300  # 5 minutes default


class ManifestPublisher:
    """Periodically re-publishes the node manifest to mDNS + UDP announcer.

    Also triggered when the bus registry changes (capability added/removed).
    """

    def __init__(
        self,
        bus,
        peer_registry,
        mdns_announcer=None,
        udp_announcer=None,
        node_manifest_fn=None,
        interval_seconds: int = _MANIFEST_REPUBLISH_INTERVAL_SECONDS,
    ) -> None:
        self._bus = bus
        self._peer_registry = peer_registry
        self._mdns_announcer = mdns_announcer
        self._udp_announcer = udp_announcer
        self._node_manifest_fn = node_manifest_fn
        self._interval = interval_seconds
        self._task: asyncio.Task | None = None

    async def run(self) -> None:
        """Publish immediately then republish every *interval_seconds*."""
        while True:
            await self._publish()
            await asyncio.sleep(self._interval)

    async def _publish(self) -> None:
        try:
            manifest = self._node_manifest_fn() if self._node_manifest_fn else {}
            caps = [c.get("name") for c in manifest.get("capabilities", [])]
            if self._mdns_announcer and hasattr(self._mdns_announcer, "republish"):
                await self._mdns_announcer.republish(caps)
            if self._udp_announcer and hasattr(self._udp_announcer, "republish"):
                await self._udp_announcer.republish()
        except Exception as exc:
            _log.debug("ManifestPublisher._publish error: %s", exc)


