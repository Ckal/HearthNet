# M15 — Relay Tier

**Spec version:** v1.0 (Phase 2)
**Depends on:** M01 (identity), M16 (tokens, for relay registration auth), X01 (transport), X05 (DHT), X04 (config)
**Depended on by:** M14 (federation, when bridges are NAT'd), M22 (mobile push delivery), X05 (DHT bootstrap)

---

## 1. Responsibility

A **relay node** is a public-internet-reachable service that helps HearthNet nodes that cannot directly reach each other (NAT, mobile networks, dynamic IPs). It provides:

- **NAT traversal**: registered nodes receive forwarded traffic from peers
- **Federation discovery**: a public lookup of "which IP currently runs community X's bridge"
- **Mobile push**: delivers chat/marketplace notifications to mobile devices via APNs/FCM
- **DHT bootstrap**: serves as a stable initial DHT endpoint

A relay is **infrastructure** — typically one or a few well-known servers per region. Christof's planned `relay.hearthnet.de` (Hetzner) is the reference deployment.

Relays do **not**:
- Store any community state long-term
- See cleartext of E2E-encrypted chat
- Make any trust decisions — they are credential-free transport for already-authenticated traffic
- Replace community anchors

---

## 2. File layout

```
hearthnet/relay/                # client-side helpers, ships with normal Hearthnet
├── __init__.py
├── client.py                   # RelayClient — registration, forwarding fetch
├── push_subscriber.py          # iOS APNs / Android FCM token registration

relay-server/                   # separate deployable, lives in /relay-server in the repo
├── pyproject.toml
├── README.md
├── relay_server/
│   ├── __init__.py
│   ├── app.py                  # FastAPI app
│   ├── registration.py         # /relay/v1/register, /heartbeat
│   ├── forward.py              # /relay/v1/forward
│   ├── lookup.py               # /relay/v1/community/<id>
│   ├── push.py                 # outbound APNs/FCM
│   ├── billing.py              # optional, for paid tier
│   ├── storage.py              # SQLite for registrations + push device tokens
│   └── observability.py        # logging, metrics
├── deploy/
│   ├── docker-compose.yml
│   ├── caddy.Caddyfile         # TLS termination
│   └── systemd/relay.service
└── tests/
```

The relay server is a thin FastAPI app deployable to any VPS. ~1500 LOC.

---

## 3. Wire surface (relay server endpoints)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/relay/v1/register` | POST | A node registers itself for forwarding |
| `/relay/v1/heartbeat` | POST | Keep registration alive |
| `/relay/v1/deregister` | POST | Cleanly remove a registration |
| `/relay/v1/forward/<node_short>` | POST | A peer wanting to reach a registered node sends the encapsulated request here |
| `/relay/v1/community/<community_id>` | GET | Look up current bridge endpoints for a community |
| `/relay/v1/push/register` | POST | Register an APNs/FCM device token for push delivery |
| `/relay/v1/push/<device_id>` | POST | Send a push notification (typically from another node) |
| `/relay/v1/dht/bootstrap` | GET | Return a list of known-good DHT contacts |
| `/relay/v1/health` | GET | Operator endpoint |

Auth: every endpoint except `/health` requires a HearthNet signature OR a relay-issued token (registered nodes get a session token for performance).

---

## 4. Public API (client-side)

### 4.1 `client.py`

```python
# hearthnet/relay/client.py
@dataclass(frozen=True)
class RelayRegistration:
    relay_url:        str
    node_id_full:     str
    expires_at:       int          # unix seconds
    session_token:    str          # short-lived bearer for subsequent calls

class RelayClient:
    """Used by federation bridges and mobile clients to be reachable through a relay."""

    def __init__(
        self,
        relay_url: str,
        kp: KeyPair,
        community_id: str,
    ):
        ...

    async def register(
        self,
        *,
        capabilities_offered: list[str] | None = None,
        external_endpoint_hint: Endpoint | None = None,
    ) -> RelayRegistration:
        """Register us with this relay. Relay will forward inbound /relay/v1/forward/<our_short>
        calls to our actual endpoint via reverse-WebSocket (we hold a persistent WS to the relay).
        Returns registration; client should hold an open WS until deregister."""

    async def heartbeat(self) -> None:
        """Refresh registration. Should be called every RELAY_REGISTRATION_TTL_SECONDS / 2."""

    async def deregister(self) -> None: ...

    async def maintain(self) -> None:
        """Long-running task: keeps registration alive, reconnects on failure."""

    # --- lookups (no registration required) ---

    async def lookup_community(self, community_id: str) -> list[Endpoint]:
        """Find current bridge endpoints for a community."""

    async def dht_bootstrap_endpoints(self) -> list[Endpoint]: ...

    async def send_push(
        self,
        device_id: str,
        payload: dict,
        *,
        push_token: str,         # token from M16 with relay.push scope
    ) -> None:
        """Send a push notification via this relay."""
```

### 4.2 `push_subscriber.py`

```python
# hearthnet/relay/push_subscriber.py
class PushSubscriber:
    """Mobile-side: registers an APNs / FCM device token with the relay
       so the relay can deliver push notifications for chat / marketplace events."""

    def __init__(
        self,
        relay_url: str,
        kp: KeyPair,
        community_id: str,
        platform: str,            # "ios" | "android" | "web"
    ):
        ...

    async def register(self, device_token: str) -> str:
        """Returns our PushDeviceID. Stored locally for later push send authorization."""

    async def unregister(self) -> None: ...
```

### 4.3 Reverse-WebSocket pattern for forwarding

NAT'd nodes can't accept inbound connections. So:

1. Node POSTs `/relay/v1/register`
2. Server returns 101 Switching Protocols, upgrading to WebSocket
3. Node holds the WS open; relay sends forwarded calls down it
4. Node processes and responds back through the same WS

The relay server's `forward.py` proxies between the inbound HTTP caller and the registered node's WS. The inbound caller sees a normal HTTP/SSE response.

---

## 5. Server-side internals (sketch)

### 5.1 Registration table

```sql
CREATE TABLE registrations (
  node_id_full TEXT PRIMARY KEY,
  community_id TEXT NOT NULL,
  external_ip TEXT,
  ws_session_id TEXT,            -- in-memory WS connection id
  capabilities_offered TEXT,     -- JSON
  registered_at INTEGER,
  expires_at INTEGER,
  last_heartbeat INTEGER
);
CREATE INDEX idx_reg_community ON registrations(community_id);
```

### 5.2 Push table

```sql
CREATE TABLE push_devices (
  device_id TEXT PRIMARY KEY,    -- ULID, assigned by relay
  node_id_full TEXT NOT NULL,
  community_id TEXT NOT NULL,
  platform TEXT NOT NULL,
  device_token TEXT NOT NULL,    -- APNs / FCM token (kept secret on relay)
  registered_at INTEGER,
  last_active INTEGER
);
CREATE INDEX idx_push_node ON push_devices(node_id_full);
```

### 5.3 Forwarding flow

```
peer P wants to call NAT'd node N (only knows N's NodeID and relay URL)
  ↓
P → POST https://relay.hearthnet.de/relay/v1/forward/<N_short>
   headers: standard X-HearthNet-* (signed by P)
   body: original capability call
  ↓
relay looks up N's WS session
  if absent → 503 relay_unreachable
  if present → wraps request as a WS message and sends to N's WS
  ↓
N processes → sends response frames back through WS
  ↓
relay streams those frames as HTTP/SSE response to P
  ↓
relay never inspects body (E2E content); relay does check signatures
   are valid (against peer manifests it caches) to prevent abuse
```

### 5.4 Push flow

```
sender wants to push to mobile user U
  ↓
sender → bus.call("auth.token.issue", scope={"capabilities":["relay.push"],"audience":"<device_id>"})
  ↓
sender → POST relay/v1/push/<device_id> with token + payload
  ↓
relay verifies token; resolves device_id → APNs/FCM token
  ↓
relay sends via APNs/FCM
  ↓
Apple/Google delivers to the device
  ↓
mobile app opens, calls bus to fetch new chat / event
```

The payload itself is opaque to the relay (`{"event_type":"chat.message.sent","sender_short":"7H4G-..."}`). The mobile app fetches the actual content via the bus when it opens.

### 5.5 Federation lookup flow

A community publishes its bridge endpoints to the relay via `/relay/v1/community/<id>` (POST, signed by an anchor). The relay caches `{community_id → [endpoints, last_updated]}` for 24 hours. GETs are free, signed (anti-spam) but lightweight.

---

## 6. Behaviour

### 6.1 Trust model

The relay is **untrusted-but-honest**. It:

- Sees who is talking to whom (NodeID-level)
- Sees signature envelopes (but not E2E ciphertext)
- Can deny service (DoS), refuse to forward, or rate-limit
- Can NOT impersonate anyone (no private keys)
- Can NOT decrypt E2E content (no DH secrets)
- Can NOT modify forwarded bytes without breaking signatures

Operators of relays are accountable through public reputation: the relay's URL is in plain sight in community configs. A misbehaving relay gets blackballed by communities.

### 6.2 Rate limiting

| Endpoint | Limit |
|----------|-------|
| `/register` | 10 per hour per node |
| `/forward` | 10 RPS per (peer, target_node) |
| `/community/<id>` GET | 100 RPS total |
| `/push/<device>` | 60 per hour per (sender, device) |

Exceeded → 429 + `retry_after_ms`.

### 6.3 Tier policy (Christof's hosted instance)

| Tier | Communities | Push notifications | Cost |
|------|-------------|--------------------|------|
| Free | ≤ 5 nodes per community | 100/day | €0 |
| Hearth | ≤ 50 nodes | 5000/day | €5/month |
| Anchor | unlimited | 50000/day | €25/month |
| Self-hosted | unlimited | unlimited | infrastructure |

The relay is open-source; any community can run their own. Hosted tier is a convenience layer.

### 6.4 Privacy guarantees

- Per-call signature verification (the relay checks them, but signatures contain only public NodeID — not user identity in a deeper sense)
- Sender hides destination by sending to `forward/<short>`; the relay sees both
- For traffic-pattern privacy (who talks to whom), no protection — outside scope
- Logs retain registration + forwarding metadata for 30 days for abuse handling, then purged

### 6.5 Failure modes

- Relay down → mobile push delivery delayed; federated lookups fall back to DHT or stored endpoints; direct LAN calls unaffected
- Relay overloaded → 429s; clients exponential-backoff
- Relay key rotation → relay publishes new pubkey signed by previous key; clients update via standard manifest refresh

---

## 7. Configuration (client side)

```python
config.relay.enabled              = False
config.relay.urls                 = ["https://relay.hearthnet.de"]
config.relay.tier                 = "free"           # informational
config.relay.register_as_bridge   = False            # if True, holds persistent WS to relay
config.relay.push_enabled         = False
config.relay.push_platform        = "web"
```

Constants: `RELAY_REGISTRATION_TTL_SECONDS=7200`, `RELAY_PUSH_RETRY_MAX=5`.

### Relay server config (`relay-server/relay_server/config.py`)

```python
config.bind                       = "0.0.0.0:443"
config.tls_cert_file              = "/etc/relay/cert.pem"
config.tls_key_file               = "/etc/relay/key.pem"
config.database                   = "/var/lib/relay/relay.db"
config.apns_cert                  = "/etc/relay/apns.pem"
config.fcm_key_file               = "/etc/relay/fcm.json"
config.tier                       = "free|hearth|anchor"
config.stripe_secret              = None             # for paid tiers
config.admin_token                = "<random>"       # for operator endpoints
```

---

## 8. Errors

`RelayError` (client domain):

- `relay_unreachable` — TCP fails or 5xx
- `registration_expired` — call requires re-register
- `forward_target_offline` — target node not currently registered with this relay
- `push_token_invalid` — APNs/FCM rejected the device token
- `tier_limit_exceeded` — quota for this tier reached

Wire mapping: `relay_unreachable` is its own code in [CAP2 §9](../CAPABILITY_CONTRACT_v2.md).

---

## 9. Tests

### Client-side unit
- `test_register_includes_signature`
- `test_heartbeat_refreshes_expires_at`
- `test_lookup_returns_endpoints`

### Server-side unit
- `test_forward_requires_target_registered`
- `test_signature_required_on_register`
- `test_rate_limit_per_peer_target`
- `test_push_dispatch_apns_mock`

### Integration
- `test_two_nat_peers_communicate_through_relay`
- `test_federation_bridge_via_relay`
- `test_push_delivered_to_real_test_device` (manual, with APNs sandbox)

### Operational
- Smoke tests on the deployed `relay.hearthnet.de` instance run hourly

---

## 10. Cross-references

| What | Where |
|------|-------|
| Token use for push auth | [M16 §5.5](M16-tokens.md) |
| Federation routes through relay | [M14 §6](M14-federation.md) |
| DHT bootstrap endpoint | [X05 §4.4](../cross-cutting/X05-dht.md) |
| Mobile push subscriber | [M22 §6](M22-mobile-native.md) |
| Wire `relay_unreachable` | [CAP2 §9](../CAPABILITY_CONTRACT_v2.md) |

---

## 11. Open questions

1. **TURN-style relay vs message relay** — current spec is message-level (peer sends entire capability call). Could also do session-level TCP relay (more efficient for streams). Phase 2.5 candidate.
2. **STUN integration** — clients could try direct connection via STUN before falling back to relay. Phase 3.
3. **Multi-relay redundancy** — a node could register with two relays for HA. MVP picks one; multi is Phase 2.5.
4. **Payment integration** — Stripe webhooks → tier upgrade. Implementation detail, not specced here.
5. **Self-hosting documentation quality** — for the "appliance" go-to-market path, the relay needs a one-command install. Defer to `RELAY_OPERATIONS.md` doc.
