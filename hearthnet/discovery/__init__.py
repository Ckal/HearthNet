from hearthnet.discovery.mdns import MdnsAnnouncer, MdnsBrowser
from hearthnet.discovery.peers import PeerEvent, PeerRecord, PeerRegistry
from hearthnet.discovery.udp import UdpAnnouncer, UdpListener


class DiscoveryError(Exception):
    """Raised for unrecoverable discovery failures (M02)."""

    def __init__(self, code: str, reason: str = "") -> None:
        super().__init__(reason or code)
        self.code = code


__all__ = [
    "DiscoveryError",
    "MdnsAnnouncer",
    "MdnsBrowser",
    "PeerEvent",
    "PeerRecord",
    "PeerRegistry",
    "UdpAnnouncer",
    "UdpListener",
]
