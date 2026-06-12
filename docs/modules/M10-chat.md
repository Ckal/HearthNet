# M10 — Chat Service

**Spec version:** v1.0
**Depends on:** M01 (identity, for signing), M03 (bus), X02 (events), X04 (config), X03 (observability), M07 (attachments via blobs)
**Depended on by:** M08 (UI chat tab)

---

## 1. Responsibility

Provide `chat.send` and `chat.history` capabilities. Handle direct-message delivery: directly if recipient is online; via store-and-forward through an anchor if offline. Maintain a per-peer chat view materialised from `chat.message.*` events.

E2E encryption between users is Phase 2 ([CONTRACT §12 open question 1](../CAPABILITY_CONTRACT.md)). MVP relies on TLS-in-transit + signed-at-rest within a trusted community.

---

## 2. File layout

```
hearthnet/services/chat/
├── __init__.py
├── service.py        # ChatService
├── delivery.py       # DeliveryManager: direct vs store-and-forward
└── views.py          # ChatView: MaterialisedView
```

---

## 3. Public API

### 3.1 `views.py`

```python
# hearthnet/services/chat/views.py
@dataclass(frozen=True)
class ChatMessage:
    event_id:     str
    lamport:      int
    sender:       str           # NodeID full form
    recipient:    str
    body:         str
    attachments:  list[dict]    # [{cid, name}]
    created_at:   str
    delivered_at: str | None
    read_at:      str | None

class ChatView:
    """MaterialisedView from chat.message.sent / .delivered / .read events."""

    def __init__(self, our_node_id_full: str):
        ...

    # MaterialisedView protocol:
    def reset(self) -> None: ...
    def apply(self, event: Event) -> None: ...
    def snapshot_state(self) -> dict: ...
    def restore_state(self, state: dict) -> None: ...

    # queries:
    def history_with(
        self,
        peer: str | None = None,
        *,
        since_lamport: int = 0,
        limit: int = 200,
    ) -> list[ChatMessage]: ...
    def peers(self) -> list[str]:
        """All NodeIDs we have exchanged messages with."""
    def unread_count(self, peer: str) -> int: ...
```

### 3.2 `delivery.py`

```python
# hearthnet/services/chat/delivery.py
class DeliveryManager:
    """Decides direct vs store-and-forward; performs delivery attempts."""

    def __init__(
        self,
        bus: CapabilityBus,
        event_log: EventLog,
        author_kp: KeyPair,
        peer_registry: PeerRegistry,
        config: ChatConfig,
    ):
        ...

    async def deliver(self, message_event: Event) -> str:
        """Attempt delivery.
        Returns: 'direct' | 'forwarded' | 'queued'.
        Strategy:
          1. Look up recipient in peer_registry.
          2. If online and reachable: push via pubsub topic chat.message.<recipient_short>.
          3. Else: pick 2 anchors with chat.store_and_forward capability (Phase 2),
                   call them with the encrypted-blob carrying message.
                   Fall back to leaving it in our log for eventual sync.
          4. Mark with method."""

    async def on_local_message_arrived(self, message_event: Event) -> None:
        """When we receive a chat.message.sent event addressed to us:
           - emit pubsub chat.message.<our_short_id> for UI
           - append chat.message.delivered event"""

    async def on_pubsub_message(self, payload: dict) -> None:
        """When the pubsub topic delivers a message to us, process it
           (which may include appending the event to our log if not already there)."""
```

### 3.3 `service.py`

```python
# hearthnet/services/chat/service.py
class ChatService:
    name    = "chat"
    version = "1.0"

    def __init__(
        self,
        config: ChatConfig,
        bus: CapabilityBus,
        event_log: EventLog,
        replay_engine: ReplayEngine,
        peer_registry: PeerRegistry,
        author_kp: KeyPair,
        our_node_id_full: str,
    ):
        self.view = ChatView(our_node_id_full=our_node_id_full)
        replay_engine.register(
            "chat",
            self.view,
            event_types=["chat.message.sent", "chat.message.delivered", "chat.message.read"],
        )
        self.delivery = DeliveryManager(bus, event_log, author_kp, peer_registry, config)

    def capabilities(self) -> list[tuple[CapabilityDescriptor, Callable, ParamsPredicate]]:
        """Registers: chat.send, chat.history."""

    async def start(self) -> None:
        """Replay; subscribe to pubsub topic chat.message.<our_short_id>."""

    async def stop(self) -> None: ...
    def health(self) -> dict: ...

    # --- handlers ---

    async def handle_send(self, req: RouteRequest) -> dict:
        """CONTRACT §4.15.
        1. Idempotency by (author, client_id).
        2. Append chat.message.sent event.
        3. DeliveryManager.deliver(event) → returns delivery method.
        4. Return {event_id, lamport, delivered}."""

    async def handle_history(self, req: RouteRequest) -> dict:
        """CONTRACT §4.16. Self-only: refuses calls where caller != our node_id."""
```

### 3.4 Capability descriptors

```python
descriptor_send = CapabilityDescriptor(
    name="chat.send", version=(1, 0), stability="stable",
    request_schema={...}, response_schema={...}, stream_schema=None,
    params={}, max_concurrent=8,
    trust_required="member", timeout_seconds=15, idempotent=True,
)

descriptor_history = CapabilityDescriptor(
    name="chat.history", version=(1, 0), stability="stable",
    request_schema={...}, response_schema={...}, stream_schema=None,
    params={}, max_concurrent=8,
    trust_required="self",          # the bus enforces caller == our_node_id
    timeout_seconds=5, idempotent=True,
)
```

The `trust_required="self"` is a new level introduced by chat. The bus interprets it as: only the local UI calling through localhost may invoke this capability. Remote callers receive `unauthorized`.

---

## 4. Behaviour

### 4.1 Send → delivery sequence

```
UI → bus.call("chat.send", (1,0), {input: {client_id, recipient, body, attachments}})
  → ChatService.handle_send
       → idempotency check
       → event_log.append_local("chat.message.sent", data, author_kp)
            ↳ this fans out to ReplayEngine which calls ChatView.apply()
       → DeliveryManager.deliver(event)
            ↳ if recipient online:
                 → publish to pubsub topic chat.message.<recipient_short>
            ↳ else (Phase 2):
                 → bus.call("chat.forward", ...) on two anchors with the capability
            ↳ else:
                 → noop, will sync via X02 eventually
       → return {event_id, lamport, delivered: "direct"|"forwarded"|"queued"}
```

### 4.2 Receive sequence

```
pubsub topic chat.message.<our_short_id> fires with event payload
  → DeliveryManager.on_pubsub_message
       → event_log.append_received(event)            (deduplicated by event_id)
            ↳ ChatView.apply()
       → event_log.append_local("chat.message.delivered", {target_event_id}, our_kp)
            ↳ propagated back to sender via gossip
       → emit local notification (UI hook)
```

### 4.3 Read receipts (optional)

When the UI scrolls past a message, it appends `chat.message.read`. If `config.chat.read_receipts_enabled = false`, the UI doesn't emit it.

### 4.4 Store-and-forward (Phase 2 stub)

MVP path: if recipient offline, message stays in our log; recipient gets it when they sync. This is fine for community members on the same LAN where everyone gossips.

Phase 2: a separate `chat.forward.put@1.0` capability registered by anchors. Sender ships the event to 2 anchors. When recipient reappears, they probe `chat.forward.fetch@1.0` against anchors. After successful delivery, anchors drop the cached event.

### 4.5 Attachments

`attachments` is a list of `{cid, name}`. The actual blob is sent separately via [M07](M07-file-blobs.md). The chat event only references the CID. Receivers fetch on demand.

### 4.6 No self-chat

`recipient == our_node_id` is rejected with `bad_request`.

### 4.7 Group chat (Phase 2)

Reserved `chat.thread.*` namespace. Out of scope here.

---

## 5. Errors

| Condition | Wire code |
|-----------|-----------|
| recipient not a community member | `not_found` |
| caller calling history but not localhost | `unauthorized` |
| empty body and no attachments | `bad_request` |
| attachment CID not known to recipient | (silent; recipient fetches via M07 on read) |

---

## 6. Configuration

From [X04 §3](../cross-cutting/X04-config.md):

```python
config.chat.enabled
config.chat.store_and_forward   # Phase 2 flag
```

Phase 2: `config.chat.read_receipts_enabled`.

---

## 7. Tests

### Unit
- `test_send_appends_event_and_returns_id`
- `test_send_idempotent_on_client_id`
- `test_history_rejects_remote_caller`
- `test_view_apply_updates_state`
- `test_self_chat_rejected`

### Integration
- `test_two_node_direct_delivery`
- `test_recipient_offline_then_online_sees_message_after_sync`
- `test_delivered_event_propagates_back_to_sender`

---

## 8. Cross-references

| What | Where |
|------|-------|
| `chat.*` wire | [CONTRACT §4.15–4.16](../CAPABILITY_CONTRACT.md) |
| Event types | [CONTRACT §7.2](../CAPABILITY_CONTRACT.md) |
| Event log | [X02](../cross-cutting/X02-events.md) |
| Attachments | [M07](M07-file-blobs.md) |
| Pubsub topics | [CONTRACT §8](../CAPABILITY_CONTRACT.md), [X01 §8](../cross-cutting/X01-transport.md) |
| UI chat tab | [M08 §5.3](M08-ui.md) |

---

## 9. Open questions

1. **E2E encryption** — Phase 2. Will use X25519 + ChaCha20-Poly1305. Body encrypted; envelope (sender, recipient, lamport) stays cleartext. Signature still over ciphertext.
2. **Group chat** — Phase 2.
3. **Voice notes** — Phase 2, would use `stt.*` for transcript, blob for audio.
4. **Phone notifications** — Phase 2, requires the relay tier.
