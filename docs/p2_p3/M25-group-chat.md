# M25 — Group Chat

**Spec version:** v2.0
**Depends on:** [M10 Chat 1:1](../../modules/M10-chat.md), [M23 E2E Encryption](M23-e2e-encryption.md), [M16 Capability Tokens](M16-tokens.md), [M03 Capability Bus](../../modules/M03-capability-bus.md), [X02 Event Log](../../cross-cutting/X02-events.md)
**Depended on by:** UI (web + M22 mobile), [M14 Federation](M14-federation.md) (cross-community threads)

---

## 1. Responsibility

Multi-party threaded conversations with the same guarantees as 1:1 chat: end-to-end encryption (optional but default on), event-log-anchored history, no central server required, members can come and go.

A thread is a long-lived object identified by a ULID. It has an authoritative member list maintained in the event log, an encryption "group session" (M23 sender keys), and message history. Threads do not currently support reactions, replies, threading-within-thread, or rich content — those are explicit non-goals for Phase 2 and may arrive in Phase 3 once usage informs design.

Group threads are the substrate the **Nachbarschaftshilfe** use case wants: a Sankt-Martins-Comité planning thread, a "Wer hat Werkzeug?" workshop thread, a household coordination thread between Christof, Jana, and grandparents.

---

## 2. File layout

```
hearthnet/services/chat/
├── thread_service.py    # ThreadService — capability registration & dispatch
├── thread_views.py      # Materialised views: thread list, member list, history
├── thread_store.py      # Read-only projections; not the source of truth
├── group_session.py     # Wraps M23 sender keys for a thread
└── moderation.py        # Phase-2: remove-member, archive — minimal
```

---

## 3. Public API

### 3.1 Dataclasses

```python
@dataclass(frozen=True)
class Thread:
    thread_id:        ThreadID
    name:             str
    created_at:       datetime
    created_by:       NodeID
    members:          frozenset[NodeID]
    e2e_enabled:      bool
    ratchet_root:     str | None      # x25519 pubkey of group session root, None if cleartext
    archived:         bool

@dataclass(frozen=True)
class ThreadMessage:
    event_id:    EventID
    thread_id:   ThreadID
    client_id:   ClientID
    sender:      NodeID
    sent_at:     datetime
    body:        str | None           # cleartext if e2e_enabled=False
    encrypted:   EncryptedPayload | None
    attachments: list[Attachment]
    delivered_to: frozenset[NodeID]   # tracked via chat.thread.message.delivered events
```

### 3.2 `ThreadService`

```python
class ThreadService:
    """Capability handlers for chat.thread.*"""

    def __init__(
        self,
        bus:                CapabilityBus,
        event_log:          EventLog,
        identity:           Identity,
        encryption:         EncryptionService,   # M23
        view_store:         ThreadViewStore,
        observability:      Observability,
    ): ...

    async def start(self) -> None:
        # Registers: chat.thread.create, .send, .history, .leave, .add_member, .archive
        ...

    # --- handlers (selected) ---
    async def create(self, body: CreateThreadBody) -> CreateThreadResult: ...
    async def send(self, body: SendThreadBody)   -> SendThreadResult: ...
    async def history(self, body: HistoryBody)   -> HistoryResult: ...
    async def leave(self, body: LeaveBody)       -> LeaveResult: ...
    async def add_member(self, body: AddMemberBody) -> AddMemberResult: ...
    async def archive(self, body: ArchiveBody)   -> ArchiveResult: ...
```

### 3.3 `ThreadViewStore`

```python
class ThreadViewStore:
    """Read model.  Backed by SQLite; rebuilt from the event log on cold start."""

    def list_for_member(self, node_id: NodeID) -> list[Thread]: ...
    def get_thread(self, thread_id: ThreadID) -> Thread | None: ...
    def get_messages(self, thread_id: ThreadID, since_lamport: int = 0, limit: int = 200) -> list[ThreadMessage]: ...
    def members_of(self, thread_id: ThreadID) -> frozenset[NodeID]: ...

    # Internal — subscribed to the event log:
    async def apply(self, event: Event) -> None: ...
```

### 3.4 `GroupSession`

Thin wrapper around M23 sender keys; one per thread.

```python
class GroupSession:
    def __init__(self, thread_id: ThreadID, ratchet: SenderKeyRatchet): ...

    def encrypt(self, plaintext: bytes) -> EncryptedPayload: ...
    def decrypt(self, sender: NodeID, payload: EncryptedPayload) -> bytes: ...
    def rekey(self) -> None: ...
    def add_member(self, new_member: NodeID, their_identity_pubkey: bytes) -> None: ...
    def remove_member(self, leaving_member: NodeID) -> None: ...
```

---

## 4. Behaviour

### 4.1 Thread creation

`chat.thread.create@1.0` flow:

1. Caller emits `chat.thread.created` event into the event log with:
   - `thread_id` (newly minted ULID)
   - initial member list
   - `e2e_enabled` flag
   - if e2e_enabled: a freshly generated `ratchet_root_pubkey` and a per-member encrypted **sender key** payload (see [M23 §6.3](M23-e2e-encryption.md))
2. Each member's node sees the event arrive, decrypts the sender key payload addressed to itself, and constructs the GroupSession.
3. The view store materialises a new Thread row.

If any member is offline at creation, they will receive the event when they next sync. Their GroupSession constructs lazily on first decrypt.

### 4.2 Sending

`chat.thread.send@1.0` flow:

1. Verify caller is in `Thread.members`.
2. If `e2e_enabled`, encrypt body with the GroupSession's current sender key. The ciphertext is opaque to the event log — even other community members who are not in the thread cannot read it.
3. Emit `chat.thread.message.sent` event.
4. The event reaches all members (regular event-log propagation, no thread-specific transport).
5. Each member's GroupSession decrypts; the message appears in their UI.

### 4.3 Membership changes

#### Adding a member

1. Any existing member can issue `chat.thread.add_member` (Phase 2; later phases may add policies like "only admin can add").
2. The caller's GroupSession is **rekeyed**: a new sender key is generated, encrypted under each existing member's pubkey and the new member's pubkey, and emitted in the `chat.thread.member.added` event.
3. The new member cannot read **prior** messages — they joined at the new epoch. (This is by design and standard for sender-key group encryption: forward-secrecy is preserved.) Old messages remain encrypted with the old sender key, which the new member never sees.

#### Removing a member

`chat.thread.remove_member` (or self-leave via `chat.thread.leave`):

1. Emit `chat.thread.member.removed`.
2. The remaining members rekey the GroupSession (similar to add but excluding the removed member). New messages are not readable by the removed member.
3. The removed member's UI marks the thread as "you left" and stops decrypting incoming messages. Their event log still contains old messages they can still read; they just can't read new ones.

### 4.4 History

`chat.thread.history@1.0`:

- **Self-only** capability (you can only ask for history of threads you're a member of).
- Returns from local view store. No cross-node query needed — every member already has the events.
- Pagination by `since_lamport` + `limit`. Messages return in **logical (Lamport) order**, not wall-clock order, to match what other members will see.

### 4.5 Read-receipts / delivery tracking

Each member's node emits `chat.thread.message.delivered` (lightweight, no payload beyond `event_id` reference) when they materialise a message. UI shows "delivered to 4/5" by counting these events. Optional — `policy.chat.delivery_receipts_enabled` (default true) controls whether they're emitted.

### 4.6 Archiving

`chat.thread.archived` is a soft state. Archived threads are hidden from the default thread list, no longer rekey on membership change, and no longer accept sends. Members can still read history. An archived thread can be unarchived by any member.

There is no "delete thread". Events are immutable. A thread that is archived and whose messages are all expired (via X02 retention policies) becomes effectively gone.

### 4.7 Attachments

`attachments` carry `cid` (blob CID) and `name`. The blob itself is uploaded via `file.put` separately. Members of the thread are by definition authorised to fetch the blob — the bus enforces this via a capability token issued automatically when sending an attachment in an E2E thread:

```
On send-with-attachment:
  1. Service issues a short-lived (24h) token via M16 with:
       scope.capabilities = ["file.fetch@1.0"]
       scope.params_constraints.cid = [attachment.cid]
       audience = thread.members  (excluding self)
  2. Token is included in the encrypted message body.
  3. Recipients use the token when fetching the blob from whichever node holds it.
```

This avoids the "file is restricted but everyone in the thread should access it" coordination problem.

### 4.8 Federation of threads

A thread MAY include members from federated communities. Mechanics:

- The thread's `community_id` (the one in event headers) is the *creator's* community.
- Members from federated communities subscribe to the thread's events via the standard federation event-bridge (see [M14 §6](M14-federation.md)).
- Federated members are full participants — they can send, leave, be removed — provided the federation manifest grants `chat.thread.send@1.0`.
- The view store on a federated member's node carries the foreign-community thread alongside their local-community threads, distinguished by `Thread.community_id` field for UI purposes.

If federation is revoked, foreign members are silently removed from the thread on the next rekey.

### 4.9 Throughput and limits

- `THREAD_MAX_MEMBERS = 200` (Phase-2 conservative; larger groups should be a different module).
- `THREAD_MAX_MESSAGE_BYTES = 64 * 1024` for the cleartext body.
- `THREAD_RATE_LIMIT_PER_SENDER_PER_MINUTE = 60` (anti-spam, enforced by ThreadService).
- Beyond these → `bad_request` or `too_many_requests`.

---

## 5. Errors

| Code | Cause |
|------|-------|
| `bad_request` | Empty member list, malformed body, member list contains caller twice |
| `unauthorized` | Caller not a member of the thread (for send/history/leave/add) |
| `not_found` | `thread_id` unknown |
| `e2e_session_missing` | Caller has no GroupSession yet (sender keys not received) |
| `e2e_decrypt_failed` | Local key state corrupt; UI should prompt for a manual rekey |
| `too_many_requests` | Rate limit exceeded |
| `policy_violation` | E.g. trying to add member outside of federation scope |

---

## 6. Configuration

```toml
[services.chat.thread]
enabled                          = true
max_members                      = 200
max_message_bytes                = 65536
rate_limit_per_sender_per_minute = 60
delivery_receipts_enabled        = true
allow_federated_members          = true

[services.chat.thread.archival]
auto_archive_after_days_idle     = 0   # 0 = never auto-archive
```

---

## 7. Tests

### 7.1 Unit
- Create thread with 3 members; verify GroupSession is constructable by each member from the `chat.thread.created` payload
- Send + decrypt round-trip
- Add member; old messages remain undecryptable for them, new ones work
- Remove member; their session can't decrypt new messages
- Self-leave; cleanup is graceful (no orphan state)
- History pagination: 1000 messages, fetch 200 + 200 + 200... covers all

### 7.2 Integration
- Three nodes on one LAN form a thread; messages propagate via gossip
- Same with one member partitioned; their replay on reconnect works
- E2E on/off threads coexist; switching one to the other is not supported (must create a new thread)
- Federation: a federated peer's node receives the `chat.thread.created` event via the bridge and constructs a working GroupSession

### 7.3 Adversarial
- A non-member tries to call `chat.thread.send` → `unauthorized`
- A non-member subscribes to `chat.thread.message.<id>` pubsub: receives encrypted blobs they can't decrypt (no information leak beyond traffic patterns and member list)
- Replay: replaying an old `chat.thread.message.sent` event by IP-level adversary is rejected by per-message nonce in the E2E header
- Rekey storm: 100 sequential add/remove operations finish within 30s on the dev rig; no deadlock

### 7.4 Performance
- 50-member thread, 1 msg/s: p95 deliver-to-decrypt latency < 500ms on LAN
- History fetch of 10,000 messages: < 2s on SSD

---

## 8. Cross-references

- Capability spec: [CAPABILITY_CONTRACT_v2 §4.16–4.19](../CAPABILITY_CONTRACT_v2.md)
- Encryption primitives: [M23 §6 sender keys](M23-e2e-encryption.md)
- Event types: [CAPABILITY_CONTRACT_v2 §7.1](../CAPABILITY_CONTRACT_v2.md#71-new-event-types)
- Federation: [M14 §6](M14-federation.md)

---

## 9. Open questions

1. **Reactions / replies / rich content** — explicitly out of Phase 2. Worth a survey of community use before designing. (Likely Phase 3 add-on, gated on "are people actually asking for it?")
2. **Per-thread retention policy** — currently inherits the community-wide retention. Different threads might want different policies (planning thread = 30 days, household chat = forever).
3. **Read-only threads** (announcements) — pseudo-thread where only one member can send. Worth a flag or worth a dedicated capability?
4. **Thread search** — could plug into `rag.*`. Indexing of decrypted message text would be opt-in per thread; raises privacy concerns.
5. **Cross-thread mentions / linking** — e.g. "see thread X for context". Probably as a UI affordance (markdown link), not a protocol feature.
6. **Disappearing messages** — Signal-style auto-expiry per-thread. Useful for sensitive coordination; adds complexity. Phase 3 candidate.
