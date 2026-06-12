from __future__ import annotations

import asyncio
import json
import time

from hearthnet.constants import (
    UDP_ANNOUNCE_INTERVAL_OFFLINE_SECONDS,
    UDP_ANNOUNCE_INTERVAL_ONLINE_SECONDS,
    UDP_MULTICAST_GROUP,
    UDP_MULTICAST_PORT,
)
from hearthnet.discovery.peers import PeerRecord, PeerRegistry
from hearthnet.types import Endpoint


class UdpAnnouncer:
    """Periodic UDP multicast of node presence."""

    def __init__(
        self,
        registry: PeerRegistry,
        node_id: str,
        community_id: str,
        port: int = 7080,
        caps: list[str] | None = None,
    ) -> None:
        self._registry = registry
        self._node_id = node_id
        self._community_id = community_id
        self._port = port
        self._caps = caps or []
        self._running = False
        self._task: asyncio.Task | None = None
        self._offline = False

    def set_offline(self, offline: bool) -> None:
        self._offline = offline

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._announce_loop(), name="udp-announcer")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            from contextlib import suppress
            with suppress(asyncio.CancelledError):
                await self._task

    async def _announce_loop(self) -> None:
        while self._running:
            await self._announce_once()
            interval = (
                UDP_ANNOUNCE_INTERVAL_OFFLINE_SECONDS
                if self._offline
                else UDP_ANNOUNCE_INTERVAL_ONLINE_SECONDS
            )
            await asyncio.sleep(interval)

    async def _announce_once(self) -> None:
        try:
            import socket

            short_id = self._node_id[8:20] if len(self._node_id) > 8 else self._node_id
            payload = json.dumps(
                {
                    "v": 1,
                    "node": short_id,
                    "community": self._community_id[:20],
                    "port": self._port,
                    "caps": self._caps[:10],
                }
            ).encode()
            if len(payload) > 1024:
                payload = payload[:1024]
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
            sock.sendto(payload, (UDP_MULTICAST_GROUP, UDP_MULTICAST_PORT))
            sock.close()
        except Exception:
            pass  # UDP failure is non-fatal


class UdpListener:
    """Receives UDP multicast announcements, populates registry."""

    def __init__(
        self,
        registry: PeerRegistry,
        our_community_id: str,
        port: int = UDP_MULTICAST_PORT,
    ) -> None:
        self._registry = registry
        self._community_id = our_community_id
        self._port = port
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._listen_loop(), name="udp-listener")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            from contextlib import suppress
            with suppress(asyncio.CancelledError):
                await self._task

    async def _listen_loop(self) -> None:
        import socket
        import struct

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)  # type: ignore[attr-defined]
            except (AttributeError, OSError):
                pass
            sock.bind(("", self._port))
            mcast_req = struct.pack("4sL", socket.inet_aton(UDP_MULTICAST_GROUP), socket.INADDR_ANY)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mcast_req)
            sock.setblocking(False)
            loop = asyncio.get_running_loop()
            while self._running:
                try:
                    data, addr = await loop.run_in_executor(None, sock.recvfrom, 2048)
                    await self._handle_packet(data, addr[0])
                except Exception:
                    await asyncio.sleep(0.1)
        except Exception:
            pass

    async def _handle_packet(self, data: bytes, source_ip: str) -> None:
        try:
            msg = json.loads(data.decode())
            if msg.get("v") != 1:
                return
            community = msg.get("community", "")
            if community and not self._community_id.startswith(community[:10]):
                return
            node_id = msg.get("node", "")
            if not node_id:
                return
            port = int(msg.get("port", 7080))
            record = PeerRecord(
                node_id_full=node_id,
                display_name=node_id[:12],
                community_id=community,
                profile="hearth",
                endpoints=[Endpoint("https", source_ip, port)],
                last_seen=time.monotonic(),
                source="udp",
            )
            self._registry.upsert(record)
        except Exception:
            pass
