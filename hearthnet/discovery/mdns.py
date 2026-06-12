from __future__ import annotations

import asyncio
import time

# Optional: python-zeroconf
try:
    from zeroconf import ServiceInfo
    from zeroconf.asyncio import AsyncServiceBrowser, AsyncZeroconf

    HAS_ZEROCONF = True
except ImportError:
    HAS_ZEROCONF = False

from hearthnet.constants import MDNS_SERVICE_TYPE
from hearthnet.discovery.peers import PeerRecord, PeerRegistry
from hearthnet.types import Endpoint


class MdnsAnnouncer:
    """Publishes our own service via mDNS. No-op if zeroconf not available."""

    def __init__(
        self,
        registry: PeerRegistry,
        node_id: str,
        display_name: str,
        port: int = 7080,
        properties: dict | None = None,
    ) -> None:
        self._registry = registry
        self._node_id = node_id
        self._display_name = display_name
        self._port = port
        self._properties = properties or {}
        self._zeroconf = None
        self._info = None

    async def start(self) -> None:
        if not HAS_ZEROCONF:
            return
        try:
            import socket

            self._zeroconf = AsyncZeroconf()
            short = self._node_id.replace("ed25519:", "")[:8]
            name = f"{self._display_name[:20]}-{short}.{MDNS_SERVICE_TYPE}"
            props = {
                "v": "1",
                "node": self._node_id,
                "profile": self._properties.get("profile", "hearth"),
                "caps": ",".join(self._properties.get("caps", [])),
                "contract_version": "1.0",
            }
            self._info = ServiceInfo(
                MDNS_SERVICE_TYPE,
                name,
                addresses=[socket.inet_aton("127.0.0.1")],
                port=self._port,
                properties={k: v.encode() for k, v in props.items()},
            )
            await self._zeroconf.async_register_service(self._info)
        except Exception:
            pass  # mDNS failure is non-fatal

    async def stop(self) -> None:
        if self._zeroconf and self._info:
            try:
                await self._zeroconf.async_unregister_service(self._info)
                await self._zeroconf.async_close()
            except Exception:
                pass


class MdnsBrowser:
    """Listens for other HearthNet nodes via mDNS, populates the registry."""

    def __init__(self, registry: PeerRegistry, our_community_id: str) -> None:
        self._registry = registry
        self._community_id = our_community_id
        self._zeroconf = None
        self._browser = None

    async def start(self) -> None:
        if not HAS_ZEROCONF:
            return
        try:
            self._zeroconf = AsyncZeroconf()
            self._browser = AsyncServiceBrowser(
                self._zeroconf.zeroconf,
                MDNS_SERVICE_TYPE,
                handlers=[self._on_service_state_change],
            )
        except Exception:
            pass

    def _on_service_state_change(self, zeroconf, service_type, name, state_change) -> None:
        self._state_change_task = asyncio.create_task(self._handle_change(zeroconf, service_type, name, state_change))

    async def _handle_change(self, zeroconf, service_type, name, state_change) -> None:
        try:
            from zeroconf import ServiceStateChange

            if state_change in (ServiceStateChange.Added, ServiceStateChange.Updated):
                info = await zeroconf.async_get_service_info(service_type, name)
                if info:
                    props = {
                        k.decode(): v.decode()
                        for k, v in info.properties.items()
                        if isinstance(k, bytes)
                    }
                    node_id = props.get("node", "")
                    if not node_id:
                        return
                    import socket

                    addresses = [socket.inet_ntoa(a) for a in info.addresses]
                    host = addresses[0] if addresses else "127.0.0.1"
                    record = PeerRecord(
                        node_id_full=node_id,
                        display_name=name.split(".")[0],
                        community_id=props.get("community", ""),
                        profile=props.get("profile", "hearth"),
                        endpoints=[Endpoint("https", host, info.port)],
                        last_seen=time.monotonic(),
                        source="mdns",
                    )
                    self._registry.upsert(record)
            # ServiceStateChange.Removed: let pruner handle it
        except Exception:
            pass

    async def stop(self) -> None:
        if self._zeroconf:
              from contextlib import suppress
              with suppress(Exception):
                  await self._zeroconf.async_close()
