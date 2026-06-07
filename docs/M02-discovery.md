# M02 — Discovery

**Spec version:** v1.0
**Depends on:** M01 (identity), X04 (config), X03 (observability), X01 (transport, for the manifest fetch URL), `python-zeroconf`
**Depended on by:** M03 (bus, for peer enumeration), M09 (emergency mode increases discovery cadence)

---

## 1. Responsibility

Find peers on the local network. Maintain a live in-memory registry of known peers with their manifests, last-seen timestamps, and latencies. Republish our own presence.

Out of scope:
- DHT (Phase 2)
- LoRa beacons (Phase 3)
- Internet relay (Phase 2)

---

## 2. File layout

```
hearthnet/discovery/
├── __init__.py
├── mdns.py              # zeroconf-based service browser + announcer
├── udp.py               # UDP broadcast announcer + listener
├── peers.py             # PeerRegistry: in-memory state
└── relay.py             # Phase 2 stub
```

---

## 3. Public API

### 3.1 `peers.py`

```python
# hearthnet/discovery/peers.py
from dataclasses import dataclass

@dataclass
class PeerRecord:
    node_id:        str             # short form
    node_id_full:   str
    display_name:   str
    community_id:   str
    profile:        str
    endpoints:      list[Endpoint]
    manifest:       NodeManifest | None  # None until fetched
    last_seen:      float           # monotonic time
    rtt_ms:         float | None    # measured by health probe
    source:         str             # "mdns" | "udp" | "relay"

class PeerRegistry:
    """In-memory map of NodeID → PeerRecord. Thread-safe via asyncio.Lock."""

    def __init__(self, our_node_id_full: str, community_id: str):
        ...

    def upsert(self, record: PeerRecord) -> bool:
        """Add or update; returns True if new peer."""

    def remove(self, node_id_full: str) -> bool: ...

    def get(self, node_id_full: str) -> PeerRecord | None: ...

    def all(self) -> list[PeerRecord]: ...

    def for_community(self, community_id: str) -> list[PeerRecord]: ...

    def prune_stale(self, max_age_seconds: int = 90) -> int:
        """Remove peers not seen recently. Returns count removed."""

    # subscribers (called when peer added / removed / updated):
    def subscribe(self) -> AsyncIterator[PeerEvent]: ...

@dataclass(frozen=True)
class PeerEvent:
    kind:   str        # "added" | "removed" | "updated"
    peer:   PeerRecord
```

### 3.2 `mdns.py`

```python
# hearthnet/discovery/mdns.py
class MdnsAnnouncer:
    """Publishes our own service via mDNS."""
    def __init__(
        self,
        kp: KeyPair,
        node_id_short: str,
        display_name: str,
        community_id_short: str,
        profile: str,
        port: int,
        capabilities_names: list[str],
        manifest_url: str,
    ):
        ...
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    def update(self, *, capabilities_names: list[str] | None = None) -> None:
        """Refresh TXT records (e.g. when capabilities change)."""

class MdnsBrowser:
    """Listens for other nodes via mDNS, populates the registry."""
    def __init__(self, registry: PeerRegistry, our_community_id: str):
        ...
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
```

### 3.3 Service definition

- Service type: `_hearthnet._tcp.local.`
- Instance name: `<display_name>-<short_node_id_4chars>`
- Port: from manifest's first endpoint
- TXT records:
  - `v=1`
  - `node=<short_node_id>`
  - `community=<short_community_id>`
  - `profile=<anchor|hearth|spark|bridge>`
  - `caps=<comma-separated cap names>` (max 200 bytes; truncate if needed)
  - `manifest_url=https://<host>:<port>/manifest`
  - `contract_version=1.0`

### 3.4 `udp.py`

```python
# hearthnet/discovery/udp.py
class UdpAnnouncer:
    """Periodic UDP multicast of node presence."""
    def __init__(
        self,
        kp: KeyPair,
        registry: PeerRegistry,
        node_id_short: str,
        community_id_short: str,
        port: int,
        capabilities_names: list[str],
        multicast_group: str = "239.255.42.42",
        multicast_port: int = 42424,
    ):
        ...
    async def run(self) -> None:
        """Loop: emit announcement every DISCOVERY_UDP_INTERVAL_SECONDS.
        Active interval when fewer than 2 peers; stable interval otherwise."""

class UdpListener:
    """Receives multicast announcements, populates registry."""
    def __init__(self, registry: PeerRegistry, our_community_id: str): ...
    async def run(self) -> None: ...
```

### 3.5 UDP payload

```json
{"v":1,"node":"7H4G-Y9KL","community":"NIED-...","port":7080,"caps":["llm.chat","rag.query"]}
```

Max 1KB. No signature on the announce itself (we'll re-fetch & verify the full manifest from `manifest_url`).

---

## 4. Behaviour

### 4.1 First contact flow

```
mDNS or UDP discovers a peer at <host:port> for community X (matches ours)
  ↓
PeerRegistry.upsert(stub PeerRecord with manifest=None)
  ↓
asyncio task: HTTP GET https://<host>:<port>/manifest (via X01 client)
  ↓
parse + verify_node_manifest (M01)
  ↓
if community matches AND author is a member (community manifest): keep
otherwise: remove
  ↓
PeerEvent("added") emitted
```

### 4.2 Refresh

- mDNS TXT updates trigger re-fetch of `/manifest`
- Every 30 seconds, we attempt to refresh peers whose manifests are within 10 seconds of expiry
- Peers whose manifests expired and could not be refetched are pruned after 90 seconds

### 4.3 Mode behaviour

When [M09](M09-emergency.md) reports offline:

- `UdpAnnouncer` switches to fast interval
- `MdnsAnnouncer` doesn't change (already low-overhead)
- Stale peer pruning becomes more aggressive (30s instead of 90s) — we want fresh data quickly

### 4.4 Multi-interface handling

- mDNS uses `zeroconf` defaults (all interfaces)
- UDP listener binds to `INADDR_ANY` on the multicast group; SO_REUSEPORT so multiple processes can coexist on the same host

### 4.5 Privacy

mDNS announces the short NodeID, profile, and a list of capability names. This is visible to any device on the LAN. We accept this — it is the price of zero-config.

Devices NOT in our community still see our presence but cannot make calls (rejected at the bus signature check).

---

## 5. Errors

`DiscoveryError` codes:

- `socket_in_use` — UDP port already bound
- `mdns_unavailable` — zeroconf fails to start (Linux without avahi, etc.)
- `manifest_fetch_failed` — HTTP error fetching `/manifest`
- `manifest_invalid` — propagated from M01 verification

Errors are logged but not fatal; the node continues with whichever discovery transport works.

---

## 6. Configuration

From [X04](X04-config.md):

```python
config.discovery.mdns_enabled
config.discovery.udp_enabled
config.discovery.udp_multicast_group
config.discovery.udp_port
config.discovery.relay_urls       # Phase 2
```

Constants: `DISCOVERY_UDP_INTERVAL_SECONDS`.

---

## 7. Tests

### Unit
- `test_peer_registry_upsert_returns_true_first_time`
- `test_peer_registry_prune_stale`
- `test_udp_payload_under_1kb`
- `test_mdns_txt_records_parse`

### Integration
- `test_two_nodes_find_each_other_via_mdns` (in-process zeroconf)
- `test_udp_fallback_when_mdns_disabled`
- `test_foreign_community_peer_filtered_out`

---

## 8. Cross-references

| What | Where |
|------|-------|
| Manifest fetch + verify | [M01 §3.2](M01-identity.md) |
| Service definition | [CONTRACT §6.1](../CAPABILITY_CONTRACT.md) (manifest schema) |
| Bus consumes peer events | [M03 §5.2](M03-bus.md) |
| Emergency mode influence | [M09 §5](M09-emergency.md) |
| Phase 2 internet relay | this module's `relay.py` (stub) |
