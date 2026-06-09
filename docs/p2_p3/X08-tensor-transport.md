# X08 — Tensor Transport

**Spec version:** v3.0 — *experimental*
**Depends on:** [X06 WebSocket](../../phase-2/cross-cutting/X06-websocket.md), [M02 Transport](../../modules/M02-transport.md), [M01 Identity](../../modules/M01-identity.md)
**Depended on by:** [M26 Distributed Inference](../modules/M26-distributed-inference.md)

---

## 1. Purpose

A binary, framed, flow-controlled transport for **tensor data** between HearthNet nodes — specifically the activations and gradients moved during M26 distributed inference. The text-oriented capability bus and JSON-shaped event envelopes are wrong for this traffic: tensors are large, dense, and benefit from binary representation, streaming, and explicit flow control.

X08 lives parallel to the bus, not on top of it. A tensor session is *negotiated* via the bus (M26 calls `pipeline.shard.connect` which returns an X08 endpoint URL and a session token), then the actual bytes move over a dedicated WebSocket binary channel.

Scope: bidirectional tensor streaming, fp16 by default, optional zstd compression above a threshold, 16-byte fixed-size headers, chunked payloads, ack-based flow control. Not a general-purpose RPC.

---

## 2. Non-goals

- **Replacing capability-bus traffic.** Control plane stays on the bus. X08 carries data only.
- **Persistent storage of tensors.** X08 is point-to-point, in-memory, ephemeral. Storage is the caller's job.
- **Cross-version negotiation of the frame format.** v3.0 ships one frame format. A future version bumps the major.
- **End-to-end encryption beyond TLS.** WebSocket runs over TLS via M02. Per-frame application-layer crypto is out of scope (the threat model doesn't require it because session establishment is authenticated, and the WSS hop is encrypted).
- **Reliable broadcast.** Sessions are 1:1. Multi-receiver fan-out is M26's problem if it needs it.

---

## 3. Wire format

### 3.1 Frame

Every frame is a single WebSocket binary message. Frame layout (big-endian):

```
offset  size   field
 0      1      version (currently 0x01)
 1      1      frame_type
 2      2      reserved (must be 0x0000)
 4      4      session_seq      (u32, monotonic per session)
 8      4      payload_length   (u32, bytes of body)
12      4      flags
16      ...    body (payload_length bytes)
```

The header is always 16 bytes. Body is opaque to the framing layer; its interpretation depends on `frame_type`.

### 3.2 Frame types

```
0x01  TENSOR_DATA          body = tensor chunk (see §3.4)
0x02  TENSOR_END           body = empty; marks last chunk of a tensor
0x03  ACK                  body = empty; acknowledges receipt up to session_seq
0x04  CONTROL_NACK         body = utf-8 error reason
0x05  CONTROL_HELLO        body = HelloMsg (json, utf-8)
0x06  CONTROL_BYE          body = utf-8 reason, optional
0x07  CONTROL_FLOWCTL      body = FlowCtlMsg (json, utf-8)
0x08  CONTROL_PING         body = 8 bytes (echo nonce)
0x09  CONTROL_PONG         body = 8 bytes (echoed nonce)
```

Frame types `0x10..0xFF` are reserved for future extensions and current implementations must close the session on unknown types.

### 3.3 Flags

```
0x00000001  COMPRESSED      payload is zstd-compressed
0x00000002  FINAL           last frame in this tensor (also implied by TENSOR_END)
0x00000004  GRAD            payload is a gradient (informational; for telemetry)
0x00000008  ENCRYPTED       reserved for future per-frame encryption
0xFFFFFFF0  reserved
```

### 3.4 Tensor chunk body

A `TENSOR_DATA` body is:

```
offset  size   field
 0      2      tensor_id        (u16, scoped to this session)
 2      1      dtype            (0x01=fp16, 0x02=fp32, 0x03=bf16, 0x04=int8)
 3      1      n_dims           (1..8)
 4      n_dims*4   shape         (u32 per dim, big-endian)
 ...           data_bytes        (compressed if COMPRESSED flag set)
```

`tensor_id` lets a session carry multiple concurrent tensors (e.g., parallel pipeline stages). A given `tensor_id` may be split across multiple `TENSOR_DATA` frames and is terminated by a `TENSOR_END` with the same `tensor_id`.

### 3.5 HelloMsg

```json
{
  "session_id": "<ulid>",
  "session_token": "<m16-token>",
  "from": "<NodeID>",
  "to": "<NodeID>",
  "purpose": "pipeline.shard.forward",
  "negotiation": {
    "preferred_dtype": "fp16",
    "compression": "zstd",
    "max_chunk_bytes": 1048576,
    "flow_window": 16
  }
}
```

Both parties exchange `CONTROL_HELLO` on connect; mismatched purposes or invalid tokens terminate the session with `CONTROL_BYE`.

### 3.6 FlowCtlMsg

```json
{ "window": 16, "credits_added": 8 }
```

Receiver-initiated. Says "I can accept N more in-flight chunks beyond what I've already acked". See §4.3.

---

## 4. Behaviour

### 4.1 Session lifecycle

```
CONNECT ──hello exchange──▶ READY ──tensor data──▶ STREAMING ──end/bye──▶ CLOSED
                  │
                  ├── auth fails ──▶ NACK ──▶ CLOSED
                  └── timeout ──▶ CLOSED
```

A session is opened by the side that initiated the bus call (the M26 caller for forward passes; the shard server for activations sent back if reverse direction is needed). The HelloMsg `session_token` is an M16 token scoped to the bus capability that authorised this session (e.g., `pipeline-shard-forward`); the receiver validates it before accepting any `TENSOR_DATA`.

### 4.2 Sequencing

`session_seq` is a u32 starting at 1 and incrementing per outgoing frame from the sender. It wraps to 1 at 2^32-1 in the theoretical case but practically a single session is expected to be far below that. Wrap is supported by the protocol but is not exercised by tests.

The receiver tracks the highest `session_seq` it has processed and acknowledges via `ACK` frames whose `session_seq` echoes the highest contiguous received seq.

### 4.3 Flow control

The receiver advertises a *credit window* in `CONTROL_FLOWCTL`. The sender may have at most `window` un-acked frames in flight. Initial window is set in `HelloMsg.negotiation.flow_window` (default `TENSOR_FLOW_CONTROL_WINDOW=16`). The receiver replenishes credits by sending `FLOWCTL` with `credits_added > 0` as it processes frames.

If the sender's in-flight count reaches the window, it pauses until an `ACK` or `FLOWCTL` arrives. There is no timeout-based unblock; if the receiver disappears, the underlying WebSocket eventually closes and the session ends.

### 4.4 Compression

`COMPRESSED` flag is set per-frame, not per-session. The sender chooses; the receiver MUST support zstd (level 3 default). Compression is applied to the *body* (everything after the 16-byte header). The body's `payload_length` reflects the compressed size; the uncompressed shape is recovered from the tensor chunk header after decompression.

Compression is enabled when the raw body exceeds `TENSOR_COMPRESSION_THRESHOLD_BYTES` (default 64 KiB). Below this, the framing overhead dominates and compression is skipped.

### 4.5 Chunking

A tensor larger than `TENSOR_CHUNK_BYTES` (default 1 MiB) is split into multiple `TENSOR_DATA` frames sharing the same `tensor_id`. The split is on raw-byte boundaries (after compression if compressed); the receiver concatenates raw bytes per `tensor_id` and then, on `TENSOR_END`, decompresses (if needed) and reconstructs the tensor using the shape declared in the *first* chunk for that `tensor_id`. Subsequent chunks for the same `tensor_id` repeat the dtype/shape header — the receiver MUST verify consistency or close the session with a NACK.

### 4.6 Keepalive

Either side may send `CONTROL_PING` at any time; the peer must respond with `CONTROL_PONG` echoing the nonce. A session with no PING/PONG and no data for `TENSOR_KEEPALIVE_SECONDS` (default 30) sends a PING; failure to respond within 2× that closes the session.

### 4.7 Backpressure & cancellation

A caller cancelling a pipeline operation (M26) sends `CONTROL_BYE` with a reason. The receiver may discard in-flight tensors for the cancelled session. There is no "graceful drain" — cancellation is fast and lossy.

### 4.8 Failure modes

- **Decompression fails**: NACK + close. The caller in M26 retries with the failover shard.
- **Tensor shape inconsistency across chunks**: NACK + close.
- **Auth failure on HelloMsg**: NACK + close before any data flows.
- **Unknown frame type**: close with NACK reason `unknown_frame_type`.
- **Sequence gap**: NACK + close. There is no out-of-order recovery; WebSocket delivers in order, so a gap means corruption.
- **Window overrun by sender**: NACK + close — the sender violated flow control.

---

## 5. API

X08 is a library, not a capability surface. Public Python API:

```python
class TensorSession:
    @classmethod
    async def connect(cls,
                       url: str,
                       token: AuthToken,
                       *,
                       purpose: str,
                       remote: NodeID,
                       negotiation: SessionNegotiation | None = None) -> TensorSession: ...
    @classmethod
    async def accept(cls,
                      ws: WebSocket,
                      *,
                      expected_purpose: str,
                      validate_token: Callable[[AuthToken], None]) -> TensorSession: ...

    async def send_tensor(self, tensor_id: int, t: Tensor, *, gradient: bool = False) -> None: ...
    async def recv_tensor(self) -> RecvTensor: ...
    async def close(self, reason: str = "") -> None: ...

    @property
    def session_id(self) -> str: ...
    @property
    def stats(self) -> SessionStats: ...

@dataclass(frozen=True)
class RecvTensor:
    tensor_id: int
    tensor:    Tensor
    is_grad:   bool

@dataclass(frozen=True)
class SessionStats:
    bytes_sent:           int
    bytes_received:       int
    bytes_compressed_out: int
    bytes_uncompressed_out: int
    frames_sent:          int
    frames_received:      int
    rtt_estimate_ms:      float
```

Implementations: `hearthnet/transport/tensor/` houses `session.py`, `frame.py`, `flow.py`, `compress.py`.

---

## 6. Configuration

```python
@dataclass(frozen=True)
class TensorTransportConfig:
    default_dtype:                 Literal["fp16","fp32","bf16","int8"] = "fp16"
    chunk_bytes:                   int = TENSOR_CHUNK_BYTES                 # 1048576
    flow_control_window:           int = TENSOR_FLOW_CONTROL_WINDOW         # 16
    compression_threshold_bytes:   int = TENSOR_COMPRESSION_THRESHOLD_BYTES # 65536
    compression_level:             int = 3                                  # zstd
    keepalive_seconds:             int = TENSOR_KEEPALIVE_SECONDS           # 30
    max_session_lifetime_seconds:  int = 3600                               # hard cap
    max_concurrent_sessions:       int = 64
    rx_buffer_bytes_max:           int = 64 * 1024 * 1024                   # 64 MiB
```

Constants in `hearthnet/constants.py`.

---

## 7. Tests

### 7.1 Unit

- `test_frame_header_layout` — pack/unpack roundtrip for all frame types.
- `test_tensor_chunk_body` — pack/unpack roundtrip for all dtypes and ranks.
- `test_compression_roundtrip` — compressed body decompresses to identity.
- `test_chunking_reassembly` — 5 MiB tensor split into 5 chunks reassembles to identical bytes.
- `test_unknown_frame_type_closes` — receiver rejects 0xFF.
- `test_flow_control_blocks_at_window` — sender pauses at window edge, resumes on ACK.
- `test_seq_gap_closes` — injecting a missing seq forces NACK + close.

### 7.2 Property

- Random tensor shapes and dtypes: send → receive → equal modulo dtype precision.
- Random chunk sizes that always sum to the same total: reassembly identical.

### 7.3 Integration

- Loopback session over an in-memory WebSocket pair: send 10 tensors of varying size, verify all received, stats consistent.
- Two-process loopback: same as above but over a real localhost WSS.
- Cancellation mid-stream: sender sends half a tensor, receives BYE, no further frames sent.
- Auth failure: connect with bad token → NACK on hello.

### 7.4 Negative

- Send to a wrong purpose → hello mismatch → close.
- Send oversized tensor (exceeds rx_buffer_bytes_max) → receiver NACKs with `tensor_too_large`.
- Corrupt frame in the middle of a tensor: receiver detects via shape inconsistency or decompression failure → close.

---

## 8. Cross-references

- **Phase 1 M02 Transport** — provides the underlying WebSocket (WSS, TLS, certificate pinning).
- **Phase 2 X06 WebSocket** — defines the WebSocket framing and reconnection semantics that X08 layers on.
- **Phase 2 M16 Tokens** — session tokens authorise tensor transport sessions.
- **Phase 3 M26 Distributed Inference** — the primary consumer; defines purposes like `pipeline.shard.forward`, `pipeline.shard.backward`.
- **Phase 3 X09 Conformance Suite** — includes optional `tensor_transport` section, only run when M26 is enabled.

---

## 9. Open questions

1. **Per-frame encryption.** The `ENCRYPTED` flag is reserved. The use case is post-quantum hardening above TLS, or end-to-end above a federation-relay path that terminates TLS at the relay. Not in v3.0.

2. **Adaptive compression.** Fixed zstd level 3 is fine for typical activations. Per-session adaptive level (lower for hot, higher for warm tensors) is plausible. Out of scope.

3. **GPU-direct transport.** Activations sit in GPU memory and round-tripping through CPU memory for serialisation is wasteful. Direct GPU-to-network (NVLink/RDMA) is interesting but assumes a specific hardware topology that HearthNet doesn't have. Not in v3.0.

4. **Multipath.** Sending tensor chunks over multiple parallel WebSocket sessions to bond bandwidth is appealing but complicates ordering. v3.0 sticks to one session.

5. **Sequence wrap.** Practically irrelevant; correctness at wrap is asserted but not battle-tested.

6. **Flow control on the wire.** Currently we layer flow control on top of WebSocket, which already has some. The duplication is intentional (we want app-level explicit windowing for backpressure into the inference scheduler) but worth revisiting.

---

*Last updated: spec v3.0.*
