# X05 — Distributed Hash Table (DHT)

**Spec version:** v1.0 (Phase 2)
**Depends on:** M01 (identity), X01 (transport), X04 (config), X03 (observability)
**Depended on by:** M14 (federation discovery), M07 ext (background blob replication via content routing), M02 ext (cross-LAN peer discovery), M15 (relay bootstrap)

---

## 1. Responsibility

Provide a Kademlia-style DHT over the internet that lets:

- A node find peers of its own community across LANs (cross-LAN extension of M02)
- A node find sources of a specific CID across communities (extension of M07's local source index)
- A node bootstrap into a federation (find an anchor of community X without knowing its IP)

Out of scope:
- Permanent storage in the DHT — DHT entries are TTL'd advertisements only
- Anonymity (no onion routing — there's no anonymity goal)
- Sybil resistance — communities are the trust roots; DHT is an unreliable hint layer

---

## 2. File layout

```
hearthnet/dht/
├── __init__.py
├── kademlia.py        # KademliaNode, routing table
├── routing.py         # FindNode, FindValue, Store, Ping RPCs
├── storage.py         # local DHT k/v store with TTL
└── bootstrap.py       # bootstrap peer list, NAT-aware reachability
```

---

## 3. Concepts

### 3.1 Key space

XOR-distance over a 256-bit key space. Keys are derived as:

- For peers: `key = blake3(node_id_full)[:32]`
- For CIDs: `key = blake3(cid_string)[:32]`
- For communities: `key = blake3(community_id_full)[:32]`

### 3.2 Bucket structure

Standard Kademlia: 256 buckets of size `DHT_REPLICATION_K = 8` (from Phase 2 constants). Concurrent lookups: `DHT_ALPHA = 3`.

### 3.3 Values stored

The DHT does **not** store community state. It stores small, signed advertisements:

| Value type | Key | Value (signed) | TTL |
|------------|-----|----------------|-----|
| Peer presence | `blake3(node_id)` | `{endpoints, community_id, expires_at}` | matches manifest TTL (30s) |
| CID source | `blake3(cid)` | `{node_id, last_seen}` | 1 hour |
| Community bootstrap | `blake3(community_id)` | `{anchor_node_ids, endpoints, manifest_url}` | 24 hours |

The DHT is a **hint cache**. Authoritative state lives in community event logs.

---

## 4. Public API

### 4.1 `kademlia.py`

```python
# hearthnet/dht/kademlia.py
from dataclasses import dataclass

@dataclass(frozen=True)
class DhtContact:
    node_key:    bytes            # 32 bytes
    node_id_full: str
    endpoint:    Endpoint
    last_seen:   float

@dataclass(frozen=True)
class DhtValue:
    """A stored advertisement. The payload is a signed dict."""
    key:        bytes
    payload:    dict              # has 'signature' field
    expires_at: int               # unix seconds

class KademliaNode:
    """One node's view of the DHT.
       Provides high-level find_node / find_value / store APIs."""

    def __init__(
        self,
        kp: KeyPair,
        endpoint: Endpoint,
        transport_client: HttpClient,
        bootstrap_endpoints: list[Endpoint],
    ):
        ...

    async def start(self) -> None:
        """Bootstrap: ping bootstrap_endpoints, populate routing table."""

    async def stop(self) -> None: ...

    # --- public lookups ---

    async def find_node(self, target_key: bytes) -> list[DhtContact]:
        """Return the k closest contacts to target_key."""

    async def find_value(self, key: bytes) -> list[DhtValue]:
        """Return values stored at this key (or empty)."""

    async def store(self, value: DhtValue) -> int:
        """Replicate to k closest nodes. Returns count of successful stores."""

    # --- maintenance ---

    async def refresh_buckets(self) -> None:
        """Per DHT_REFRESH_SECONDS: ping a random key in each bucket to liveness-check it."""

    async def republish_values(self) -> None:
        """Per DHT_REPUBLISH_SECONDS: re-store our own advertisements so TTL doesn't expire them."""

    # --- introspection ---

    def routing_table_size(self) -> int: ...
    def stored_values(self) -> int: ...
```

### 4.2 `routing.py`

Wire RPCs exposed by the bus transport (X01) as additional endpoints under `/dht/v1/`:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/dht/v1/ping` | POST | Liveness, exchange contact info |
| `/dht/v1/find_node` | POST | Return k closest contacts to a key |
| `/dht/v1/find_value` | POST | Return values at a key OR closest contacts if absent |
| `/dht/v1/store` | POST | Accept a value into local storage (if we're among the k closest) |

```python
# hearthnet/dht/routing.py
async def serve_ping(req: dict) -> dict: ...
async def serve_find_node(req: dict, kademlia: KademliaNode) -> dict: ...
async def serve_find_value(req: dict, kademlia: KademliaNode) -> dict: ...
async def serve_store(req: dict, kademlia: KademliaNode) -> dict: ...

# Request / response shapes documented inline in each function.
```

### 4.3 `storage.py`

```python
# hearthnet/dht/storage.py
class DhtStore:
    """Local key-value store with TTL eviction.
       Backing: SQLite in <DATA>/dht/store.sqlite."""

    def __init__(self, db_path: Path):
        ...

    def put(self, value: DhtValue) -> bool:
        """Idempotent. Returns True if stored (we're in k closest), False if rejected."""

    def get(self, key: bytes) -> list[DhtValue]:
        """Return non-expired values for this key."""

    def evict_expired(self) -> int: ...

    def size(self) -> int: ...
```

### 4.4 `bootstrap.py`

```python
# hearthnet/dht/bootstrap.py

DEFAULT_BOOTSTRAP_NODES: list[Endpoint] = [
    # Filled at packaging time with community-run bootstrap endpoints.
    # Christof's relay.hearthnet.de will be a default.
]

async def is_reachable(endpoint: Endpoint, timeout_seconds: float = 5) -> bool:
    """Send a ping; return True if responded."""

async def discover_external_ip() -> str | None:
    """Use STUN against a public STUN server to learn our external IP.
       Used by relay-assisted bootstrap to advertise reachable endpoints."""
```

---

## 5. Behaviour

### 5.1 Advertisement lifecycle

```
Node starts → KademliaNode.start()
  → ping bootstrap_endpoints; build initial routing table
  → store our peer presence: store(DhtValue(blake3(node_id), {...}, ttl=30s))
  → store community bootstrap: store(DhtValue(blake3(community_id), {anchors, ...}, ttl=24h))
  → for each pinned CID: store(DhtValue(blake3(cid), {node_id, ...}, ttl=1h))
  ↓
Every MANIFEST_REPUBLISH_INTERVAL_SECONDS: re-store peer presence
Every DHT_REPUBLISH_SECONDS: re-store all our advertisements
Every DHT_REFRESH_SECONDS: refresh routing table buckets
```

### 5.2 Lookup integration with M02

When [M02 PeerRegistry](../../modules/M02-discovery.md) doesn't find a peer for a known community on the LAN:

```python
# M02 extension (Phase 2)
async def find_remote_peers(community_id: str) -> list[PeerRecord]:
    if dht is None:
        return []
    contacts = await dht.find_value(blake3(community_id))
    candidates = [parse_community_bootstrap(v.payload) for v in contacts]
    return await fetch_manifests_and_filter(candidates, community_id)
```

### 5.3 Lookup integration with M07

When [M07 TransferManager](../../modules/M07-file-blobs.md) needs sources for a CID and the local `file.cid.advertised` index is empty:

```python
# M07 extension (Phase 2)
async def find_remote_sources(cid: str) -> list[str]:  # NodeIDs
    contacts = await dht.find_value(blake3(cid))
    return [parse_source_advert(v.payload).node_id for v in contacts]
```

### 5.4 Signature requirement on stored values

Every DHT value's `payload` must contain a `signature` field signed by the advertiser. Receivers reject values whose signature does not validate against the advertiser's claimed NodeID. Cost is small; protection is essential — without it, anyone can poison the DHT.

### 5.5 NAT traversal hooks

The DHT itself does not do hole-punching. It cooperates with [M15 Relay Tier](../M15-relay-tier.md):

- If our advertised endpoint is unreachable (NAT'd), we additionally advertise `via_relay: "<relay_url>"` in the value payload
- Peers wanting to reach us see the relay hint and route through it
- Direct peer-to-peer over NAT (STUN/TURN) is Phase 3

### 5.6 Privacy of the DHT

The DHT is a public-internet-facing component (by definition). It leaks:
- Which NodeIDs exist
- Which communities exist
- Which CIDs are popular

It does **not** leak:
- The contents of any blob
- The contents of community event logs
- Who's actually a member of a community (membership is in the signed manifest, fetched out of band)

This is acceptable for a system whose goal is community resilience, not anonymity.

### 5.7 Anti-spam

- Per-source rate limit on `store` calls: max 100 per minute per node
- Stored value size cap: 4 KB
- Per-bucket eviction prefers values with higher signature reputation (Phase 3)

### 5.8 Bootstrap reachability

`bootstrap_endpoints` (from config) are tried in order. If all fail, the node logs a warning and continues with mDNS+UDP only. The DHT is best-effort.

---

## 6. Wire format (request/response examples)

### 6.1 `POST /dht/v1/find_value`

Request:
```json
{
  "key":      "blake3:<hex of 32 bytes>",
  "from":     "ed25519:<our NodeID>",
  "trace_id": "01HXR...",
  "signature": "ed25519:<over the above three fields canonicalised>"
}
```

Response (value found):
```json
{
  "values": [
    {
      "key":     "blake3:...",
      "payload": {"node_id":"...","endpoints":[...],"signature":"ed25519:..."},
      "expires_at": 1717942800
    }
  ]
}
```

Response (not found, get closer contacts):
```json
{
  "values":  [],
  "closer":  [{"node_id_full":"ed25519:...","endpoint":{"host":"...","port":7080}}, "..."]
}
```

---

## 7. Errors

`DhtError`:

- `bootstrap_failed` — no bootstrap endpoint reachable
- `lookup_timeout` — couldn't find value or contacts within DHT_LOOKUP_TIMEOUT
- `store_unauthorized` — payload signature invalid
- `value_too_large` — > 4 KB
- `rate_limited` — per-source store rate exceeded

These don't always map to wire codes — most DHT activity is internal to the node. When they bubble up to a caller, `dht_lookup_failed` is the wire code.

---

## 8. Configuration

```python
config.dht.enabled                  = False  # opt-in; phase 1 default off
config.dht.bootstrap_endpoints      = [...]
config.dht.public_endpoint_override = None   # for nodes behind NAT, manual override
config.dht.advertise_cids           = True   # also advertise pinned CIDs
config.dht.advertise_community      = True
```

Constants used: `DHT_REPLICATION_K=8`, `DHT_ALPHA=3`, `DHT_REFRESH_SECONDS=3600`, `DHT_REPUBLISH_SECONDS=86400`.

---

## 9. Tests

### Unit
- `test_xor_distance_metric`
- `test_routing_table_insert_eviction`
- `test_signed_value_verification`
- `test_unsigned_value_rejected`
- `test_ttl_eviction`

### Integration
- `test_three_node_dht_find_value` — three KademliaNodes in process, store, find
- `test_bootstrap_picks_up_existing_dht`
- `test_partition_then_reconnect_converges`
- `test_value_republish_keeps_alive`

### Property-based
- `test_kademlia_eventual_consistency_under_churn` (Hypothesis-driven)

---

## 10. Cross-references

| What | Where |
|------|-------|
| Used by federation bootstrap | [M14 §4.3](../modules/M14-federation.md) |
| Used by background blob replication | M07 ext (see [00-OVERVIEW §1](../00-OVERVIEW.md)) |
| Wire error code | `dht_lookup_failed` in [CAP2 §9](../CAPABILITY_CONTRACT_v2.md) |
| Phase 1 alternative (mDNS/UDP) | [M02](../../modules/M02-discovery.md) |
| Phase 3 sybil resistance | TBD |

---

## 11. Open questions

1. **libp2p reuse vs custom Python.** libp2p has a Python port but it's heavyweight. A focused 1000-LOC Kademlia matches our needs and stays auditable. Decision: custom for now; can swap.
2. **NAT hole punching.** Currently relay-only. STUN/TURN integration is Phase 3.
3. **Public DHT vs federated DHTs.** Should the DHT itself be federated (per-community DHT joined via cross-sig)? Maybe. Defer.
4. **Onion routing.** Out of scope. HearthNet has no anonymity goal.
