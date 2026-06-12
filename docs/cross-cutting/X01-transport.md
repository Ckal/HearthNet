# X01 — Transport

**Spec version:** v1.0
**Depends on:** M01 (identity), X04 (config), X03 (observability), FastAPI, uvicorn, httpx
**Depended on by:** M03 (bus), M02 (discovery, indirectly), X02 (sync endpoints)

---

## 1. Responsibility

Moves bytes between nodes over HTTP/1.1+TLS. Provides:

- An HTTP server hosting the bus, pubsub, sync, and metrics endpoints
- An HTTP client with TLS pinning and signature signing
- Server-Sent Events (SSE) for streaming
- Backpressure on streams (window-based)
- Rate limiting per (peer, capability)
- Self-signed TLS cert generation and pinning

This module knows nothing about *what* it transports. It dispatches calls to the bus, which routes to services.

---

## 2. File layout

```
hearthnet/transport/
├── __init__.py
├── server.py            # FastAPI app factory + lifecycle
├── client.py            # HttpClient: signed requests, TLS pinning
├── streams.py           # SSE writer/reader, frame parsing
├── backpressure.py      # Window-based flow control
└── tls.py               # Cert load/generate, peer pinning store
```

---

## 3. HTTP server

### 3.1 Public API

```python
# hearthnet/transport/server.py
from fastapi import FastAPI
from typing import Awaitable, Callable

class HttpServer:
    def __init__(
        self,
        config: TransportConfig,
        kp: KeyPair,
        bus: 'CapabilityBus',
        event_sync: 'SyncServer',
        community_manifest_provider: Callable[[], CommunityManifest],
    ):
        ...

    def app(self) -> FastAPI:
        """The configured FastAPI app. Used by tests."""

    async def run(self) -> None:
        """Block, serving until cancelled."""

    async def shutdown(self) -> None: ...
```

### 3.2 Endpoints (mounted)

| Route | Method | Purpose | Handler |
|-------|--------|---------|---------|
| `/bus/v1/call` | POST | Capability call (sync or stream) | bus dispatch |
| `/manifest` | GET | Current node manifest JSON | identity |
| `/community/manifest` | GET | Current community manifest | identity |
| `/sync/v1/heads` | GET | Sync heads | X02 |
| `/sync/v1/events` | POST | Sync delta | X02 |
| `/pubsub/v1/subscribe` | GET (long-poll) | Topic subscription | bus pubsub |
| `/health` | GET | Liveness | observability |
| `/ready` | GET | Readiness (≥1 capability + ≥1 peer) | observability |
| `/metrics` | GET | Prometheus | observability |
| `/trace/recent` | GET | Last N traces (JSON) | observability |

`/mobile/*` for the mobile web client is mounted by [M08](../modules/M08-ui.md) outside transport's concern.

### 3.3 Request lifecycle

```
HTTP request arrives
  ↓
extract X-HearthNet-* headers
  ↓
verify signature (M01) using X-HearthNet-From
  ↓
check author is a community member (community manifest)
  ↓
attach trace (X03) from X-HearthNet-Request-Id
  ↓
rate-limit check (this module)
  ↓
dispatch to bus.handle_call(capability, version, body, caller)
  ↓
return response (or stream)
```

Failures at each stage emit a typed error matching [CONTRACT §9](../CAPABILITY_CONTRACT.md).

---

## 4. TLS

### 4.1 Cert generation

On first run, generate a self-signed X.509 certificate with:

- Subject CN = `<short_node_id>.hearthnet.local`
- SAN = `IP:<config.transport.host>` if not 0.0.0.0, else all interfaces
- Public key derived from the device Ed25519 key (Ed25519 is a TLS 1.3 signature algorithm)
- Valid for 10 years (covers normal device life)

Cert + key persisted at `<DATA>/tls/server.crt` and `<DATA>/tls/server.key`.

### 4.2 Pinning store

```python
# hearthnet/transport/tls.py
class PinnedCerts:
    """Stores the first-seen TLS cert fingerprint per NodeID.
       Mismatches on subsequent connections raise a warning and refuse the connection."""

    def __init__(self, db_path: Path): ...
    def record(self, node_id: str, fingerprint: bytes) -> None: ...
    def expected(self, node_id: str) -> bytes | None: ...
    def verify(self, node_id: str, presented: bytes) -> bool: ...
```

### 4.3 Hostname verification

Disabled. We pin to NodeID, not DNS. Peers are referenced by IP+port from manifests.

---

## 5. HTTP client

### 5.1 Public API

```python
# hearthnet/transport/client.py
class HttpClient:
    def __init__(
        self,
        kp: KeyPair,
        node_id: str,
        community_id: str,
        pinned_certs: PinnedCerts,
        timeout_default_seconds: float = RPC_DEFAULT_TIMEOUT_SECONDS,
    ):
        ...

    async def call(
        self,
        peer: Endpoint,
        capability: str,
        version: str,
        body: dict,
        *,
        trace_id: str | None = None,
        timeout_seconds: float | None = None,
    ) -> dict:
        """Sync RPC. Signs request, opens TLS connection (or reuses pinned),
        sends, awaits response, verifies response signature if present,
        returns body. Raises CallError on transport / protocol failure."""

    async def stream(
        self,
        peer: Endpoint,
        capability: str,
        version: str,
        body: dict,
        *,
        trace_id: str | None = None,
        cancel: asyncio.Event | None = None,
    ) -> AsyncIterator[Frame]:
        """Open SSE stream. Yields Frame objects (event_name + data dict).
        Honours backpressure: sends ACK frames automatically.
        On cancel: closes connection, server aborts within 200ms."""

    async def close(self) -> None: ...

class CallError(Exception):
    code: ErrorCode
    message: str
    retry_after_ms: int | None
    alt_capabilities: list[str]
    alt_nodes: list[str]
```

### 5.2 Connection management

- One `httpx.AsyncClient` per peer, reused across calls
- Idle timeout `CONNECTION_IDLE_SECONDS` (60s), then close
- On disconnect, lazy reconnect on next call
- Reconnect backoff: exponential, cap `RECONNECT_BACKOFF_CAP_SECONDS` (30s)

### 5.3 Signing

For every outbound request, the client constructs:

```python
envelope = {
    "capability": capability,
    "version":    version,
    "request_id": trace_id or new_ulid(),
    "from":       node_id_full,
    "community":  community_id,
    "timestamp":  rfc3339_now(),
    "body":       body,
}
sig = kp.sign_bytes(canonical_json(envelope))
```

Headers set: `X-HearthNet-Capability`, `-Version`, `-Request-Id`, `-From`, `-Community`, `-Timestamp`, `-Signature`.

---

## 6. Streaming

### 6.1 SSE writer (server)

```python
# hearthnet/transport/streams.py
class SseWriter:
    def __init__(self, response: StreamingResponse): ...
    async def emit(self, event: str, data: dict) -> None: ...
    async def emit_token(self, token: dict) -> None: ...     # convenience
    async def emit_progress(self, current: int, total: int, stage: str) -> None: ...
    async def emit_error(self, code: ErrorCode, **kwargs) -> None: ...
    async def emit_done(self, **meta) -> None: ...
    async def emit_ack(self, upto: int) -> None: ...
    @property
    def cancelled(self) -> bool: ...
```

### 6.2 SSE reader (client)

```python
class SseReader:
    async def __aiter__(self) -> AsyncIterator[Frame]: ...
    async def cancel(self) -> None: ...

@dataclass(frozen=True)
class Frame:
    event: str        # "token", "chunk", "progress", "ack", "done", "error", "manifest", "ready", ...
    data:  dict
    seq:   int        # local sequence number for backpressure
```

### 6.3 Backpressure

```python
# hearthnet/transport/backpressure.py
class FlowControl:
    """Window-based flow control for one stream."""
    def __init__(self, window: int = STREAM_WINDOW_FRAMES, ack_interval: int = STREAM_ACK_INTERVAL_FRAMES):
        ...

    @property
    def window_used(self) -> int: ...
    def send(self) -> None: ...           # call before emitting a frame; blocks (await) when full
    def ack(self, upto: int) -> None: ...

    @property
    def needs_ack(self) -> bool: ...      # reader checks this; emits ack frame
```

### 6.4 Cancellation

- Client closes the HTTP connection
- Server's request task is cancelled
- Service handler's generator receives `GeneratorExit` (or async equivalent)
- Service emits final telemetry and exits within 200ms
- A finally block guarantees resources are freed

---

## 7. Rate limiting

```python
# hearthnet/transport/__init__.py (or rate_limit.py)
class RateLimiter:
    """Token-bucket per (peer, capability) and per peer total."""
    def __init__(self, config: TransportConfig): ...

    def check(self, peer_node_id: str, capability: str) -> RateCheck:
        """Returns ok, soft-limited, or hard-limited.
        Soft → return 429 with retry_after_ms
        Hard → drop without response (logged + counter)."""

@dataclass(frozen=True)
class RateCheck:
    allowed:        bool
    soft_exceeded:  bool
    retry_after_ms: int
```

Limits from constants:
- `RATE_LIMIT_SOFT_RPS_PER_CAP = 10`
- `RATE_LIMIT_HARD_RPS_PER_CAP = 100`
- `RATE_LIMIT_SOFT_RPS_TOTAL = 100`
- `RATE_LIMIT_HARD_RPS_TOTAL = 1000`

---

## 8. Pub-sub (long-poll)

```python
# hearthnet/transport/server.py (sub-component)
class PubSubServer:
    """In-memory topic registry; long-poll subscribers."""

    async def publish(self, topic: str, payload: dict) -> None: ...

    async def subscribe(self, topic: str, *, last_seq: int = 0, timeout_seconds: float = 30) -> dict:
        """Long-poll: returns next message or {timeout: true} after timeout_seconds."""
```

`/pubsub/v1/subscribe?topic=marketplace.post.created&last_seq=0&timeout=30`

WebSocket variant deferred to Phase 2.

---

## 9. Errors

Server returns errors in the format of [CONTRACT §5.4](../CAPABILITY_CONTRACT.md). Client raises `CallError` carrying the same code.

---

## 10. Configuration

From [X04](X04-config.md):

```python
config.transport.host
config.transport.port
config.transport.tls_cert      # optional override
config.transport.tls_key       # optional override
```

Constants: `STREAM_WINDOW_FRAMES`, `STREAM_ACK_INTERVAL_FRAMES`, `STREAM_ACK_TIMEOUT_SECONDS`, `RPC_DEFAULT_TIMEOUT_SECONDS`, `CONNECTION_IDLE_SECONDS`, `RECONNECT_BACKOFF_CAP_SECONDS`, `RATE_LIMIT_*`.

---

## 11. Tests

### Unit
- `test_request_signing_roundtrip` — sign on client, verify on server
- `test_envelope_canonicalisation` — same input → same signature
- `test_sse_frame_format` — parses both ways
- `test_flow_control_blocks_when_full` — `send()` awaits until ack arrives
- `test_rate_limit_soft_then_hard`
- `test_tls_pinning_first_seen_then_mismatch`

### Integration
- `test_two_node_call_roundtrip`
- `test_stream_with_cancellation`
- `test_concurrent_streams_share_connection`
- `test_chaos_packet_loss_30pct` (using `tc`)

---

## 12. Cross-references

| What | Where |
|------|-------|
| Wire format | [CONTRACT §5](../CAPABILITY_CONTRACT.md) |
| Signing rules | [CONTRACT §10](../CAPABILITY_CONTRACT.md), [M01 §3.1](../modules/M01-identity.md) |
| Bus dispatch | [M03](../modules/M03-bus.md) |
| Sync endpoints | [X02 §6](X02-events.md) |
| Pub-sub topics | [CONTRACT §8](../CAPABILITY_CONTRACT.md) |
| Mobile UI mount point | [M08](../modules/M08-ui.md) |
