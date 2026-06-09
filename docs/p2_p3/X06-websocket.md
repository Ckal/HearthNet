# X06 — WebSocket Upgrade

**Spec version:** v1.0 (Phase 2)
**Depends on:** X01 (transport), X03 (observability), `websockets` Python library
**Depended on by:** X01 transport server (in-place extension), M21 (tool-call loops), M25 (group chat live), M22 (mobile push delivery)

---

## 1. Responsibility

Add bidirectional WebSocket transport alongside the existing HTTP/1.1 + SSE in [X01](../../cross-cutting/X01-transport.md). Use cases:

- Tool-call loops in `llm.chat` where the server needs to ask the client to execute a tool mid-stream
- Live pubsub topics that fan out many messages per second (group chat, federation heartbeats)
- Mobile clients on flaky cellular where reconnect is expensive

WebSockets do **not** replace the request/response model. They are an *upgrade* available on specific endpoints when both ends support v2 contract.

---

## 2. File layout

```
hearthnet/transport/
└── websocket.py        # WebSocket server-side handler + client-side wrapper
```

Single file; the protocol is small.

---

## 3. Endpoints supporting upgrade

| Endpoint | Behaviour |
|----------|-----------|
| `/bus/v1/call` | When `Upgrade: websocket` present and capability descriptor supports streaming, upgrade and use frame protocol on the WS instead of SSE |
| `/pubsub/v1/subscribe` | When upgraded, server pushes messages on topic without long-polling |
| `/sync/v1/events` | NOT upgraded — sync is bursty and short-lived; HTTP fits |

---

## 4. WebSocket frame protocol

WebSocket frames carry the **same JSON event/data envelope** as SSE. This is deliberate — handlers can be written once and dispatched to either transport.

### 4.1 Outbound (server → client)

Each WebSocket message is one JSON object:

```json
{"event": "token", "data": {"text": "Hallo "}, "seq": 12}
```

`seq` is monotonic per-stream from the server. Used for backpressure ACKs.

### 4.2 Inbound (client → server)

Two kinds of messages:

#### Backpressure ACK

```json
{"type":"ack","upto":8}
```

#### Tool result (mid-stream)

```json
{"type":"tool_result","tool_call_id":"tc_01HXR...","body":{...}}
```

Used in tool-call loops (see [M21](../modules/M21-tool-calls.md)).

#### Cancel

```json
{"type":"cancel"}
```

Cleanly stops the current operation. Server must abort within 200 ms and emit a final `error` or `done` frame.

### 4.3 Control frames

Standard WebSocket pings/pongs. `WEBSOCKET_PING_SECONDS = 30` between pings.

---

## 5. Public API

### 5.1 Server side

```python
# hearthnet/transport/websocket.py
class WebSocketSession:
    """Wraps a WebSocket connection from the server's perspective."""

    def __init__(self, ws: WebSocket, kp: KeyPair):
        ...

    @property
    def closed(self) -> bool: ...
    @property
    def remote_node_id(self) -> str: ...

    async def emit(self, event: str, data: dict) -> None:
        """Send a frame; respect flow control."""

    async def emit_token(self, token: dict) -> None: ...
    async def emit_progress(self, current: int, total: int, stage: str) -> None: ...
    async def emit_error(self, code: ErrorCode, **kwargs) -> None: ...
    async def emit_done(self, **meta) -> None: ...

    async def receive(self) -> WsClientFrame | None:
        """Block until a client frame arrives, or None on close."""

    async def close(self, code: int = 1000) -> None: ...

@dataclass(frozen=True)
class WsClientFrame:
    type:         str          # "ack" | "tool_result" | "cancel"
    data:         dict
```

### 5.2 Client side

```python
class WebSocketClient:
    """Used by HttpClient (X01) when stream() is called with `prefer_ws=True`."""

    def __init__(
        self,
        url: str,
        kp: KeyPair,
        community_id: str,
        pinned_certs: PinnedCerts,
    ):
        ...

    async def open(self) -> None: ...
    async def close(self) -> None: ...

    async def send_call(
        self,
        capability: str,
        version: str,
        body: dict,
        *,
        trace_id: str,
    ) -> None:
        """Initial call frame. Authentication via X-HearthNet-* headers
        and a signed call-envelope sent as the first WS message."""

    async def __aiter__(self) -> AsyncIterator[Frame]:
        """Yields Frame objects (same shape as SSE Frame)."""

    async def send_tool_result(self, tool_call_id: str, body: dict) -> None: ...
    async def send_ack(self, upto: int) -> None: ...
    async def cancel(self) -> None: ...
```

### 5.3 Upgrade negotiation on the server

X01's [HttpServer](../../cross-cutting/X01-transport.md) gets a small dispatch shim:

```python
# in hearthnet/transport/server.py (Phase 2 extension)
async def dispatch_call(request: Request):
    if request.headers.get("upgrade") == "websocket" and capability_supports_stream(...):
        return await dispatch_via_websocket(request)
    else:
        return await dispatch_via_sse_or_json(request)
```

`capability_supports_stream` checks the descriptor's `stream_schema` is not None.

---

## 6. Behaviour

### 6.1 Handshake

```
client → GET /bus/v1/call
         Connection: Upgrade
         Upgrade: websocket
         Sec-WebSocket-Protocol: hearthnet-bus.v2
         (other X-HearthNet-* headers)
  ↓
server: validates capability + initial signature
        responds 101 Switching Protocols if v2 capable
        responds 426 Upgrade Required (with downgrade hint) if not v2
  ↓
client sends first message: signed call envelope
        {"type":"call","envelope":{...},"signature":"ed25519:..."}
  ↓
server: validates signature, dispatches to bus
  ↓
server streams response frames; client streams ACKs / tool_results / cancels
```

### 6.2 Flow control

Same window-based FC as SSE (`STREAM_WINDOW_FRAMES = 16`, ACK every 8). Server checks `flow_control.send()` before each emit; client sends `ack` messages every 8 received frames.

### 6.3 Idle handling

If no message in either direction for `WEBSOCKET_IDLE_CLOSE_SECONDS` (120s), server closes with code 1000. Client may reopen.

### 6.4 Failure modes

| Symptom | Behaviour |
|---------|-----------|
| Client disconnect mid-stream | Server's task receives `CancelledError`, aborts the underlying capability within 200ms |
| Network drop | Either side's WS library raises; current stream is `error`-terminated locally |
| Server overload | Server may decline upgrade with 503 + retry hint; client falls back to SSE |
| Protocol version mismatch | Server replies 426 with `Sec-WebSocket-Protocol` listing supported versions |

### 6.5 Pubsub via WS

Subscribing to a topic via WS:

```
client GET /pubsub/v1/subscribe?topic=marketplace.post.created
       Upgrade: websocket
  ↓
server upgrades; sends backlog (if `since_seq` provided) then live messages
  ↓
each message: {"event":"published","data":{...},"seq":N}
  ↓
client sends ACKs to allow server to advance flow control
```

This replaces the long-polling pattern from Phase 1 §8 for clients that hold the connection. The long-poll endpoint remains for non-WS clients.

### 6.6 Tool-call loop (used by [M21](../modules/M21-tool-calls.md))

```
server emits:
  {"event":"token","data":{"text":"..."}}
  {"event":"tool_call_delta","data":{"id":"tc_1","name":"rag.query","arguments_delta":"..."}}
  ...
  {"event":"tool_call","data":{"id":"tc_1","arguments":{"query":"...","corpus":"..."}}}
client must respond:
  {"type":"tool_result","tool_call_id":"tc_1","body":{...result of bus.call("rag.query",...)...}}
server continues:
  {"event":"token","data":{"text":"Based on the documents..."}}
  ...
  {"event":"done","data":{...}}
```

Without WebSocket, the SSE-only fallback is for the *caller* (UI) to execute the tool and re-call `llm.chat` with the tool result added to messages. Both paths work; WS is more efficient.

---

## 7. Errors

`WebSocketError` codes (local domain):

- `upgrade_refused` — server returned 426 or 503
- `version_unsupported` — protocol mismatch
- `idle_timeout`
- `bad_frame` — malformed JSON or invalid `type`

On the wire, errors carried inside the WS as `event: error` frames map to the standard wire codes in [CAP §9](../../CAPABILITY_CONTRACT.md).

---

## 8. Configuration

```python
config.transport.websocket_enabled       = True
config.transport.websocket_idle_close_seconds = WEBSOCKET_IDLE_CLOSE_SECONDS
config.transport.websocket_ping_seconds  = WEBSOCKET_PING_SECONDS
```

---

## 9. Tests

### Unit
- `test_ws_frame_shape_matches_sse`
- `test_signed_call_envelope_first_message`
- `test_invalid_signature_closes_connection`
- `test_idle_close_after_timeout`

### Integration
- `test_two_node_ws_call_round_trip`
- `test_ws_stream_tokens_then_done`
- `test_ws_tool_result_inline`
- `test_ws_cancel_within_200ms`
- `test_ws_fallback_to_sse_when_426`
- `test_pubsub_via_ws_backlog_plus_live`

### Chaos
- `test_ws_dropped_packet_recovery` (using `tc`)

---

## 10. Cross-references

| What | Where |
|------|-------|
| Endpoint upgrade | [CAP2 §5.1](../CAPABILITY_CONTRACT_v2.md) |
| Frame protocol shared with SSE | [X01 §6](../../cross-cutting/X01-transport.md), [CAP §5.3](../../CAPABILITY_CONTRACT.md) |
| Tool-call loop | [M21](../modules/M21-tool-calls.md) |
| Mobile client benefits | [M22 §5](../modules/M22-mobile-native.md) |
| Phase 3 considerations (WebTransport / QUIC) | TBD |

---

## 11. Open questions

1. **HTTP/3 / WebTransport** — Phase 3 candidate; better on mobile, doesn't need TCP setup time on reconnect.
2. **Binary frames** — JSON works; binary CBOR could save bytes. Defer until profiling shows it matters.
3. **Multiplexing many capability calls on one WS** — currently one WS per call. Multiplex possible but adds complexity. Defer.
4. **WSS certificate handling** — same TLS pinning as HTTPS; works because WS goes over the same TLS connection.
