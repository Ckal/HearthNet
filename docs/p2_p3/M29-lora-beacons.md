# M29 — LoRa Hardware Beacons

**Spec version:** v3.0 — *experimental*
**Depends on:** [M03 Capability Bus](../../modules/M03-capability-bus.md), [M02 Transport](../../modules/M02-transport.md), [X02 Event Log](../../cross-cutting/X02-events.md), [M11 Notifications](../../modules/M11-notifications.md), [M01 Identity](../../modules/M01-identity.md)
**Depended on by:** Civil Defense (M31) optionally consumes beacon-presence signals

---

## 1. Responsibility

Optional **out-of-band presence and panic-button channel** over 868 MHz LoRa hardware. When the internet is out, when the cellular network is down, when the power grid is wobbly — the LoRa stack still carries a 32-byte "I exist" ping or a tiny panic message between neighbours up to a few kilometres apart.

This module is explicitly **not a data channel**. No AI traffic, no chat content, no file transfer. The bandwidth is laughably small (sub-100 bytes per minute per node in a normal duty-cycle regime), the latency is awful, and the airwave is shared. What LoRa is good at is "I'm still here, and the gateway in the next village is still reachable."

The module exposes a small set of capabilities for sending and receiving beacons, mapping LoRa device IDs to HearthNet identities, and surfacing the resulting connectivity graph to the rest of the stack as a fallback signal. Hardware is a USB-attached LoRa stick (RFM95W, sx1276, sx1262 chipsets) bridged via serial.

---

## 2. Non-goals

- **General-purpose meshing of HearthNet over LoRa.** Bandwidth and duty cycle make this impossible at any useful scale.
- **Encryption of beacon contents.** Beacons carry identity hash + sequence + minimal flags only. Anything sensitive belongs on a different channel.
- **Replacing TETRA/BOS.** Emergency services have their own radio. This is a *neighbour-to-neighbour* fallback, not a replacement for professional emergency comms.
- **Hardware abstraction layer for every LoRa chipset.** v3.0 supports a small whitelist (RFM95W, sx1276, sx1262 via Meshtastic-firmware sticks). Others are open contributions.
- **Long-distance routing.** No multi-hop store-and-forward in v3.0. A beacon goes one hop or it doesn't go.
- **Legal interpretation of national radio regulations.** Each operator is responsible for complying with their local rules (BNetzA in Germany, ETSI in EU, FCC in US). The module enforces *configured* duty-cycle limits but cannot enforce the law on the operator.

---

## 3. File layout

```
hearthnet/lora/
├── __init__.py
├── service.py           # LoraBeaconService — the capability handler
├── serial_bridge.py     # USB-serial framing to the LoRa stick
├── frame.py             # Encode/decode the 32-byte beacon frame
├── duty_cycle.py        # Track airtime, enforce duty-cycle limits
├── peer_map.py          # LoRa device ID ↔ NodeID mapping (with TOFU verification)
└── adapters/
    ├── __init__.py
    ├── meshtastic.py    # Meshtastic firmware stick
    ├── rfm95w.py        # Bare RFM95W via serial-port gateway firmware
    └── sx126x.py        # sx1262 module
```

---

## 4. Public API

### 4.1 Dataclasses

```python
LoraBeaconID = NewType("LoraBeaconID", str)         # device-local sequence + prefix
LoraDeviceID = NewType("LoraDeviceID", str)         # hardware ID from the stick

@dataclass(frozen=True)
class LoraBeacon:
    beacon_id:       LoraBeaconID
    sender_hash:     bytes                # 4-byte truncated SHA-256 of sender NodeID
    sequence:        int                  # u16, wraps
    flags:           int                  # u8 bit-field; see §5.2
    rssi:            int | None           # dBm, on receive only
    snr:             float | None         # dB, on receive only
    timestamp:       datetime             # local clock at decode

@dataclass(frozen=True)
class LoraPeer:
    node_id:         NodeID
    device_id:       LoraDeviceID
    sender_hash:     bytes
    first_seen:      datetime
    last_seen:       datetime
    rssi_recent:     int | None
    verified_tofu:   bool                 # True after operator confirmation

@dataclass(frozen=True)
class DutyCycleStatus:
    region:          Literal["EU868","US915","AS923"]
    window_seconds:  int
    airtime_used_ms: int
    airtime_budget_ms: int                # e.g. 36000 ms in EU868 1% window
    next_tx_allowed_at: datetime
```

### 4.2 Capabilities

All under `experimental.lora.*`:

```python
async def lora_status() -> LoraStatus
async def lora_beacon_send(flags: int = 0) -> LoraBeaconID
async def lora_panic_send() -> LoraBeaconID                 # sets FLAG_PANIC; bypasses normal pacing
async def lora_peer_list() -> list[LoraPeer]
async def lora_peer_verify(device_id: LoraDeviceID, node_id: NodeID) -> VerifyReceipt
async def lora_recent_beacons(since: datetime | None = None) -> list[LoraBeacon]
async def lora_duty_cycle() -> DutyCycleStatus
async def lora_subscribe_beacons() -> AsyncIterator[LoraBeacon]
```

### 4.3 Service class

```python
class LoraBeaconService:
    def __init__(self,
                 bus: CapabilityBus,
                 event_log: EventLog,
                 notifications: NotificationService,
                 identity: IdentityService,
                 config: LoraConfig): ...

    async def start(self) -> None: ...                 # opens serial, begins RX loop
    async def stop(self) -> None: ...
    async def send_beacon(self, flags: int = 0) -> LoraBeaconID: ...
    async def send_panic(self) -> LoraBeaconID: ...
    async def on_frame_received(self, raw: bytes, rssi: int, snr: float) -> None: ...
    async def _drain_rx(self) -> None: ...
    def duty_cycle_status(self) -> DutyCycleStatus: ...
```

### 4.4 Serial bridge

```python
class SerialBridge:
    def __init__(self, port: str, baud: int = 115200, adapter: LoraAdapter = ...): ...
    async def open(self) -> None: ...
    async def close(self) -> None: ...
    async def write(self, frame: bytes) -> None: ...
    async def read(self) -> AsyncIterator[bytes]: ...

class LoraAdapter(Protocol):
    """Per-chipset/firmware framing rules."""
    name: str
    def encode_tx(self, payload: bytes) -> bytes: ...
    def decode_rx(self, raw: bytes) -> tuple[bytes, int, float]: ...  # payload, rssi, snr
    def at_init_commands(self) -> list[bytes]: ...
```

---

## 5. Behaviour

### 5.1 Beacon frame

Strictly 32 bytes, big-endian:

```
offset  size  field
 0      1     version (currently 0x01)
 1      4     sender_hash (SHA-256(NodeID)[:4])
 5      2     sequence (u16, wraps)
 7      1     flags
 8      1     reserved (0x00)
 9      4     unix_seconds (sender's clock, u32; informational only)
13      19    payload (currently zero-padded; reserved for future use)
```

No payload content is carried beyond identity-hash + flags + clock. The flags field carries:

```python
FLAG_PANIC          = 0x01   # urgent attention requested
FLAG_OK             = 0x02   # explicit "I'm fine" (operator pressed an OK button)
FLAG_GATEWAY        = 0x04   # this node has an alternate transport currently up
FLAG_LOW_BATTERY    = 0x08   # device-level low-battery indicator
FLAG_RESERVED_*     = 0x10..0x80
```

Frames are not encrypted. Frames *are* not anonymous either — the sender hash is small enough to collide (4 bytes), but stable enough that a passive observer can correlate beacons from the same sender over time. This is documented and acceptable for the threat model: LoRa airwaves are observable by construction.

### 5.2 RX path

1. `SerialBridge` yields raw frames as they arrive.
2. `LoraAdapter.decode_rx` peels off the chipset framing and returns the 32-byte payload + RSSI + SNR.
3. `service.on_frame_received` validates: length == 32, version == 0x01, sender_hash plausibly maps to a known or unknown peer.
4. If `sender_hash` matches a verified peer in `peer_map`, the beacon is recorded against that peer.
5. If `sender_hash` is unknown, a `lora.peer.unknown` event is emitted with a TOFU verification prompt for the operator.
6. If `FLAG_PANIC` is set, a high-priority notification is raised via M11 regardless of peer-verification status.
7. The beacon is published on the bus subscription `experimental.lora.beacon.received`.

### 5.3 TX path and duty cycle

Beaconing follows a fixed cadence `LORA_BEACON_PERIOD_SECONDS` (default 600 = 10 minutes). Each transmission's airtime is computed from spreading factor and bandwidth (typical: SF9, BW125 → ~165 ms per 32-byte frame) and added to the duty-cycle window.

The duty-cycle window enforces the region's regulation:

| Region | Window | Budget |
|--------|--------|--------|
| EU868 | 3600 s | 36 s (1%) |
| US915 | 3600 s | unlimited (FHSS) but config still applies |
| AS923 | 3600 s | 36 s (1%) |

If a normal `send_beacon` call would exceed the budget, it is **deferred** until the budget allows. `send_panic` ignores the duty-cycle limit (regulations universally permit emergency transmissions). The operator is told via notification that the duty-cycle override was used and the event log records `lora.duty_cycle.overridden`.

### 5.4 Peer mapping (TOFU)

The first time a `sender_hash` is received, the module emits a notification: *"A new LoRa peer with hash 0xABCD1234 was heard. Do you recognise this device?"* The operator can:

- **Verify by NodeID** — provide a HearthNet NodeID; the module checks that `SHA-256(NodeID)[:4] == sender_hash` and stores the verified mapping.
- **Mark as unknown** — store the hash with no NodeID; future beacons from this hash will still be tracked but flagged unknown.
- **Block** — drop all beacons from this hash; never prompt again.

Hash collisions (two different NodeIDs producing the same 4-byte hash) are possible but unlikely. When two operators independently verify the same hash to different NodeIDs, the conflict is surfaced as a `lora.peer.conflict` event for manual resolution.

### 5.5 Beacon-presence signal

Other modules can subscribe to `experimental.lora.beacon.received` to incorporate "this peer is alive on LoRa even though the internet says they're offline" into their own logic. M31 Civil Defense in particular uses this to corroborate that a target node is alive during an outage incident.

The presence signal is *advisory*: a node that beacons on LoRa is alive in the radio sense, but that says nothing about whether the operator is responsive or whether higher-layer services are available there.

### 5.6 Failure modes

- **No stick attached or USB error:** `lora.status()` reports `unavailable`. The module starts in a disabled state; no errors are raised on startup, only logged.
- **Stick attached but firmware mismatch:** `at_init_commands` fail; the adapter raises `lora_hardware_unsupported` and the service stays disabled.
- **Receive flood:** the RX queue is bounded (`LORA_RX_QUEUE_MAX` default 256). Overflow drops oldest entries and emits a `lora.rx.dropped` event.
- **Clock skew:** beacons carry the sender's clock, but the receiver never trusts it for ordering — local arrival timestamp is authoritative.
- **Adversarial flooding:** an attacker on 868 MHz can spam frames; the duty-cycle limits *us* but not *them*. The service rate-limits beacons per `sender_hash` at the RX side (`LORA_PEER_RX_MAX_PER_MINUTE`, default 20) to avoid filling notifications. Excess beacons from one hash are dropped silently after the rate limit; this is a known DoS vector and documented in §10.

---

## 6. Errors

| Code                          | When                                                             |
|-------------------------------|------------------------------------------------------------------|
| `experimental_disabled`       | Capability called with the flag off                              |
| `lora_hardware_unavailable`   | No stick present or serial port not opened                       |
| `lora_hardware_unsupported`   | Adapter init failed; firmware not whitelisted                    |
| `lora_duty_cycle_exhausted`   | Non-panic send requested with budget at zero and override off    |
| `lora_peer_unknown`           | `lora.peer.verify` for a sender_hash we've never seen            |
| `lora_peer_conflict`          | verify() would create a (hash → two distinct NodeIDs) mapping    |
| `lora_frame_malformed`        | RX frame fails structural validation                             |

---

## 7. Configuration

```python
@dataclass(frozen=True)
class LoraConfig:
    enabled:                bool = False
    serial_port:            str = "/dev/ttyUSB0"     # also Windows COM4, etc.
    serial_baud:            int = 115200
    adapter:                Literal["meshtastic","rfm95w","sx126x"] = "meshtastic"
    region:                 Literal["EU868","US915","AS923"] = "EU868"
    spreading_factor:       int = 9                  # 7..12; higher = more range, less rate
    bandwidth_khz:          int = 125
    coding_rate_denom:      int = 5                  # 4/5
    tx_power_dbm:           int = 14                 # legal max for EU868
    beacon_period_seconds:  int = LORA_BEACON_PERIOD_SECONDS_DEFAULT       # 600
    panic_burst_count:      int = 3                  # PANIC sends this many frames rapid-fire
    panic_burst_gap_ms:     int = 800
    rx_queue_max:           int = LORA_RX_QUEUE_MAX                        # 256
    peer_rx_max_per_minute: int = LORA_PEER_RX_MAX_PER_MINUTE              # 20
    tofu_auto_accept:       bool = False             # never auto-trust new hashes by default
    duty_cycle_override_for_panic: bool = True
```

Constants live in `hearthnet/constants.py`.

---

## 8. Tests

### 8.1 Unit

- `test_frame_encode_decode_roundtrip` — random payloads encode to exactly 32 bytes and round-trip.
- `test_sender_hash_matches_nodeid` — `SHA-256(NodeID)[:4]` matches the field in the encoded frame.
- `test_duty_cycle_tracks_airtime` — synthetic transmissions accumulate; budget drains; recovers over time.
- `test_panic_overrides_duty_cycle` — `send_panic` succeeds at zero budget when override is enabled.
- `test_panic_blocked_when_override_disabled` — `send_panic` returns `lora_duty_cycle_exhausted` when override is off.
- `test_peer_rx_rate_limit` — 30 frames from one hash within a minute → only 20 surface.

### 8.2 Integration (loopback)

- Mock `SerialBridge` echoes TX as RX after a configurable delay. Verify a sent beacon shows up in `recent_beacons` and on the subscription.
- Two simulated nodes (separate SerialBridges connected via an in-memory channel) — A sends, B receives, B's peer_map contains A after TOFU verification, RSSI/SNR are populated.

### 8.3 Hardware-in-the-loop (optional)

- With a real LoRa stick, send N beacons and verify duty-cycle accounting matches what the firmware reports.
- Range test: two sticks at increasing distance; record packet-loss vs distance.

### 8.4 Negative

- Disabled flag → all capabilities return `experimental_disabled`.
- No serial port → `lora_hardware_unavailable` on status.
- Truncated frame → `lora_frame_malformed`, dropped.
- Conflicting verify → `lora_peer_conflict`.

---

## 9. Cross-references

- **Phase 1 M01 Identity** — `SHA-256(NodeID)[:4]` is the sender hash; verification uses M01's NodeID type.
- **Phase 1 M02 Transport** — LoRa is *not* a Transport in the M02 sense. It does not carry capability-bus traffic; it lives parallel to M02 as an alternative signalling channel. The two share no code.
- **Phase 1 M11 Notifications** — high-priority panic-beacon notifications and TOFU prompts route through M11.
- **Phase 1 X02 Event Log** — `lora.*` events.
- **Phase 3 M31 Civil Defense** — beacon-presence is one corroborating signal for "is the target node alive" during an incident.
- **Phase 3 X09 Conformance Suite** — LoRa is an optional capability; conformance tests use a mock serial bridge.

---

## 10. Open research questions

1. **Mesh routing.** Multi-hop store-and-forward over LoRa is well-explored in the Meshtastic project. Whether HearthNet should adopt it (and inherit the bandwidth tradeoffs) or keep one-hop simplicity is unsettled. Probably belongs in M29b.

2. **Authenticated beacons.** Adding even a 4-byte MAC would let receivers reject forged sender-hashes. This costs payload space we don't have today. A 64-byte frame variant (`version 0x02`) with HMAC-truncated-to-8-bytes is the obvious extension.

3. **DoS robustness.** Per-hash rate limiting is naive; an attacker just rotates hashes. The defence on 868 MHz is mostly the regulatory duty-cycle and physical proximity, neither of which we control in software. Documented as a known limitation.

4. **Sleep-and-wake duty cycles.** Battery-powered nodes (a panic button by the bedside) want to sleep most of the time and wake on demand. Class-A/B/C LoRaWAN-style scheduling is the standard answer. Out of scope for v3.0.

5. **Chipset coverage.** v3.0 supports a small whitelist. Each new chipset is an adapter shaped exactly like the existing ones; contributors are encouraged.

6. **GPS integration.** Many LoRa sticks ship with a GPS module. We deliberately did not surface location data in v3.0 — location is privacy-sensitive and the use case is unclear. A future `FLAG_HAS_GPS` + paired side-channel might make sense for civil-defence scenarios.

7. **Integration with civil-defence radio.** TETRA-BOS and BOS-Digitalfunk are professional networks we have no business interoperating with. But a *unidirectional* "did the BOS station broadcast a known alert" listener might be useful. Legally complex.

8. **Network coding.** When multiple nearby nodes beacon, the airwave fills. Cooperative beacon scheduling (so neighbours don't transmit on top of each other) is a fun problem. Currently each node beacons independently and collisions are accepted.

---

*Last updated: spec v3.0.*
