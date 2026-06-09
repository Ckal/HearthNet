# M23 — End-to-End Encryption

**Spec version:** v1.0 (Phase 2)
**Depends on:** M01 (identity, key derivation), M07 (blobs, for prekey bundles), X02 (events, for prekey/session events), X04 (config), `pynacl`
**Depended on by:** M10 chat (extended), M25 group chat, optionally M07 file encryption

---

## 1. Responsibility

Provide end-to-end encryption between community members for:

- **1:1 chat** (via M10 extension): every chat message encrypted with a per-sender ratchet
- **Group chat** (M25): per-thread sender keys
- **File envelopes** (M07 extension): chunks optionally wrapped in a per-recipient envelope

The cryptographic design borrows from Signal but stays simpler:

- **X3DH** for initial key agreement (one identity key + one signed prekey + one one-time prekey)
- **Double Ratchet** for per-session forward-secrecy
- **Sender keys** (Signal-style) for group threads
- **Per-blob envelope** for file encryption

This module owns the crypto primitives and session state. M10 and M25 own the message protocol that calls into M23.

---

## 2. File layout

```
hearthnet/crypto/
├── __init__.py
├── kem.py             # X25519 key agreement (X3DH)
├── ratchet.py         # Double Ratchet, per-session
├── sender_keys.py     # Group sender keys (M25 helper)
├── envelope.py        # File envelope encryption (chunks)
└── prekeys.py         # Prekey bundle storage and publication
```

The `hearthnet/crypto/` directory is a NEW top-level package in Phase 2.

---

## 3. Public API

### 3.1 `kem.py` — X3DH

```python
# hearthnet/crypto/kem.py
from dataclasses import dataclass

@dataclass(frozen=True)
class X25519KeyPair:
    private: bytes        # 32 bytes
    public:  bytes        # 32 bytes "x25519:<base64>"

def x25519_generate() -> X25519KeyPair: ...
def x25519_dh(our_priv: bytes, their_pub: bytes) -> bytes:
    """Computes the shared secret. 32 bytes."""

@dataclass(frozen=True)
class PrekeyBundle:
    """What a recipient publishes so senders can establish a session without them being online."""
    node_id_full:        str
    identity_pub:        bytes               # long-lived; derived from Ed25519 identity via SignedConversion
    signed_prekey_pub:   bytes
    signed_prekey_sig:   bytes               # Ed25519 signature over signed_prekey_pub by identity Ed25519 key
    one_time_prekeys_pub: list[bytes]        # depleted on use
    published_at:        int                 # unix seconds

def derive_identity_x25519_from_ed25519(ed_kp: KeyPair) -> X25519KeyPair:
    """Use the standard nacl conversion. Single x25519 identity key per device."""

def build_prekey_bundle(
    ed_kp: KeyPair,
    *,
    num_one_time: int = E2E_PREKEY_BUNDLE_SIZE,
) -> tuple[PrekeyBundle, X25519KeyPair, list[X25519KeyPair]]:
    """Returns (bundle, signed_prekey_full, one_time_prekeys_full).
       Caller persists the private halves; publishes only the bundle."""

def x3dh_initiator(
    our_identity_x: X25519KeyPair,
    our_ephemeral: X25519KeyPair,
    their_bundle: PrekeyBundle,
) -> tuple[bytes, dict]:
    """Returns (shared_secret, session_init_message).
       session_init_message includes our identity_pub + ephemeral_pub + used_otp_index."""

def x3dh_responder(
    our_identity_x: X25519KeyPair,
    our_signed_prekey: X25519KeyPair,
    our_one_time_prekey: X25519KeyPair | None,
    their_identity_pub: bytes,
    their_ephemeral_pub: bytes,
) -> bytes:
    """Returns shared_secret."""
```

### 3.2 `ratchet.py` — Double Ratchet

```python
# hearthnet/crypto/ratchet.py
@dataclass
class RatchetState:
    """One session, one direction. There are two per session (send + receive)."""
    root_key:      bytes
    chain_key:     bytes
    counter:       int
    epoch:         int
    skipped_messages: dict[tuple[int, int], bytes]  # (epoch, counter) → message_key
    dh_keypair:    X25519KeyPair | None
    remote_dh_pub: bytes | None

@dataclass
class RatchetSession:
    """A bidirectional encrypted session between two NodeIDs."""
    peer_node_id_full: str
    send_state:    RatchetState
    recv_state:    RatchetState

    def is_established(self) -> bool: ...

def init_session_initiator(shared_secret: bytes, peer_dh_pub: bytes) -> RatchetSession: ...
def init_session_responder(shared_secret: bytes, our_dh_kp: X25519KeyPair) -> RatchetSession: ...

@dataclass(frozen=True)
class RatchetMessageHeader:
    dh_pub:     bytes       # current sender's DH pub
    epoch:      int
    counter:    int

def encrypt_message(
    session: RatchetSession,
    plaintext: bytes,
    *,
    aad: bytes = b"",
) -> tuple[RatchetMessageHeader, bytes]:
    """Returns (header, ciphertext). Mutates session.send_state."""

def decrypt_message(
    session: RatchetSession,
    header: RatchetMessageHeader,
    ciphertext: bytes,
    *,
    aad: bytes = b"",
) -> bytes:
    """Verifies + decrypts. Mutates session.recv_state.
       Tolerates up to E2E_RATCHET_MAX_OUT_OF_ORDER out-of-order messages via skipped_messages."""

class RatchetError(Exception):
    """code in {
       'session_not_established','decrypt_failed','out_of_order_too_far',
       'message_too_old','aad_mismatch'}"""
    code: str

# Persistence: sessions are serialised via dataclasses_json into a SQLite table.
```

### 3.3 `sender_keys.py` — Group ratchet

```python
# hearthnet/crypto/sender_keys.py
@dataclass
class SenderKeyState:
    """Per (group, sender) sender-key chain. Each sender broadcasts a chain key
       to all group members at thread create / join."""
    thread_id:       str
    sender_node_id:  str
    chain_key:       bytes
    counter:         int
    signature_keypair: tuple[bytes, bytes] | None    # ed25519, for message signing

@dataclass
class GroupSession:
    """One per thread; holds all members' SenderKeyStates."""
    thread_id:    str
    sender_keys:  dict[str, SenderKeyState]    # sender_node_id → state

def init_sender_key(thread_id: str, sender_node_id: str) -> SenderKeyState: ...
def encrypt_for_group(session: GroupSession, sender_node_id: str, plaintext: bytes) -> tuple[dict, bytes]: ...
def decrypt_for_group(session: GroupSession, header: dict, ciphertext: bytes) -> bytes: ...

def serialise_sender_key_distribution(state: SenderKeyState) -> bytes:
    """Serialise a sender key for sending to other group members.
       MUST be sent inside a pairwise Double Ratchet session, not in cleartext."""

def consume_sender_key_distribution(bytes_blob: bytes, session: GroupSession) -> None: ...
```

### 3.4 `envelope.py` — File envelope

```python
# hearthnet/crypto/envelope.py
@dataclass(frozen=True)
class FileEnvelopeHeader:
    recipient_node_ids: list[str]
    wrapped_keys:       dict[str, bytes]      # node_id_short → wrapped symmetric key
    nonce:              bytes                  # 12 bytes
    chunk_size_bytes:   int

def encrypt_blob_for(
    recipients: list[str],                    # NodeIDs full
    plaintext: bytes,
    sender_kp: KeyPair,
    sessions_provider: Callable[[str], RatchetSession | None],
) -> tuple[FileEnvelopeHeader, bytes]:
    """1. Generate random 32-byte symmetric key
    2. For each recipient: encrypt key with their ratchet session (one-shot use of next message key)
    3. ChaCha20-Poly1305-encrypt plaintext with the symmetric key + nonce
    4. Return (header, ciphertext)"""

def decrypt_blob_for_self(
    header: FileEnvelopeHeader,
    ciphertext: bytes,
    our_node_id_full: str,
    sessions_provider: Callable[[str], RatchetSession | None],
) -> bytes:
    """1. Find our wrapped key in header.wrapped_keys
    2. Decrypt symmetric key via sender's ratchet session
    3. ChaCha20-Poly1305-decrypt"""
```

### 3.5 `prekeys.py` — Publication and consumption

```python
# hearthnet/crypto/prekeys.py
class PrekeyStore:
    """Persists this node's private prekey material and the bundles we've consumed for others."""

    def __init__(self, db_path: Path):
        ...

    def publish_self(
        self,
        ed_kp: KeyPair,
        event_log: EventLog,
        *,
        num_one_time: int = E2E_PREKEY_BUNDLE_SIZE,
    ) -> None:
        """1. Build PrekeyBundle (kem.build_prekey_bundle)
        2. Persist private halves locally
        3. Emit e2e.prekeys.published event with public halves"""

    def get_peer_bundle(self, peer_node_id_full: str) -> PrekeyBundle | None:
        """Look in local cache; if absent, fetch from peer via bus.
        Returns one bundle including one consumable one-time prekey if available."""

    def consume_one_time_prekey(self, our_otp_index: int) -> X25519KeyPair | None:
        """Server-side: when someone uses one of our one-time prekeys, return + remove it."""

    def refill_one_time_prekeys_if_low(self, ed_kp: KeyPair, event_log: EventLog) -> int:
        """If fewer than E2E_PREKEY_BUNDLE_SIZE / 4 remain, publish a new bundle.
        Returns count added."""
```

---

## 4. Behaviour

### 4.1 Session establishment lifecycle (1:1)

```
Alice wants to send Bob an encrypted message; no session exists.
  ↓
PrekeyStore.get_peer_bundle("ed25519:bob") → fetch from Bob's most recent e2e.prekeys.published event
  ↓
x3dh_initiator(alice_identity_x, alice_ephemeral, bob_bundle) → (shared_secret, init_msg)
  ↓
init_session_initiator(shared_secret, bob_signed_prekey_pub) → RatchetSession
  ↓
encrypt_message(session, plaintext) → (header, ciphertext)
  ↓
Alice sends: chat.message.sent event with data.body = {
   "e2e": true,
   "header": { x3dh_init: init_msg, ratchet_header: header },
   "ciphertext": "<base64>"
}
  ↓
Bob receives event.
   x3dh_responder(...) → shared_secret
   init_session_responder(...) → RatchetSession
   decrypt_message(...) → plaintext
   Emit e2e.session.established event so Alice can clean up retries
  ↓
Subsequent messages: just header + ciphertext (no x3dh_init).
```

### 4.2 Group session establishment

```
Thread creator emits chat.thread.created with members and an ed25519:thread_signing_root.
  ↓
Each member generates a SenderKeyState for themselves in this thread.
  ↓
Each member, in a pairwise loop, sends their sender key distribution to each other member
   inside their 1:1 ratchet sessions (so non-thread-members never see it).
  ↓
Once everyone has everyone's sender keys, encrypt/decrypt happens with sender keys
   (chain ratchet only; no DH ratchet on the group session itself).
```

When a member is added later, the inviter must re-distribute all existing senders' current chain states to the new member (rewinds to the message they should start being able to read — usually the current state, not history).

When a member is removed, existing sender keys are still known to them. **All members must rotate their sender keys** to achieve forward secrecy after removal. UI prompts this.

### 4.3 Out-of-order messages

Up to `E2E_RATCHET_MAX_OUT_OF_ORDER` (32) skipped message keys are cached per session. Beyond that, `out_of_order_too_far` is raised; the message is dropped and the sender notified (out-of-band) that they should rekey.

### 4.4 Rekeying

After `E2E_RATCHET_REKEY_AFTER_MESSAGES` messages on the same DH ratchet, the next message includes a new DH ephemeral. Standard Double Ratchet behaviour. Transparent to users.

### 4.5 Session loss recovery

If a node's session state is lost (disk corruption, fresh install with same keys), the peer doesn't know — messages will fail to decrypt. Recovery flow:

1. Decrypting node returns `e2e_decrypt_failed` via pubsub
2. Sending node sees this and re-initiates X3DH
3. New session replaces old; resends recent messages

UI shows "session was reset" so users know context might have been lost.

### 4.6 Identity X25519 derivation

We derive a per-device X25519 identity key from the Ed25519 identity key, using libsodium's `crypto_sign_ed25519_pk_to_curve25519`. This way:

- Only one identity key to maintain
- Anyone with the public Ed25519 (in the community manifest) can derive the X25519 pub
- Signed prekey signatures use the Ed25519 key (already established as device identity)

### 4.7 Prekey publication

Each node publishes a fresh `e2e.prekeys.published` event on startup if their last one is > 24h old. The event contains:

- `identity_pubkey` (X25519 form)
- `signed_prekey` (with Ed25519 signature)
- `one_time_prekeys[]` (up to `E2E_PREKEY_BUNDLE_SIZE` = 20)

Consumers find a peer's bundle by reading their latest `e2e.prekeys.published` event from the log.

### 4.8 What is NOT E2E

Even with M23 active:
- Event envelope (sender, recipient, lamport, event_type, wall_clock) is cleartext within the community
- Signatures over events remain valid for community-level audit
- Message *metadata* leaks to community members (who talked to whom and when), just not content

This is intentional: communities are trust roots; complete anonymity within a community is not a goal.

### 4.9 File envelope

For file blobs, `encrypt_blob_for(recipients, plaintext, ...)` produces a single ciphertext, with a small per-recipient header. Senders pick recipients explicitly (e.g. group thread members for an attachment). Bystanders cannot decrypt even if they fetch the blob via M07 `file.read`.

The blob's CID is the hash of the **ciphertext**, so the same plaintext sent to different recipient sets has different CIDs. Costs more storage; needed for security.

---

## 5. Persistence

### 5.1 Sessions table

```sql
CREATE TABLE ratchet_sessions (
  peer_node_id_full TEXT PRIMARY KEY,
  session_blob      BLOB NOT NULL,        -- serialised RatchetSession
  established_at    INTEGER NOT NULL,
  last_used         INTEGER NOT NULL
);
```

### 5.2 Group sessions table

```sql
CREATE TABLE group_sessions (
  thread_id        TEXT PRIMARY KEY,
  session_blob     BLOB NOT NULL,
  updated_at       INTEGER NOT NULL
);
```

### 5.3 Prekey private halves

```sql
CREATE TABLE prekey_private (
  kind TEXT NOT NULL,                     -- 'identity'|'signed_prekey'|'one_time'
  index_or_id TEXT NOT NULL,              -- '0' for identity; 'spk_v1' for signed; otp index for OTPs
  private_key BLOB NOT NULL,
  consumed_at INTEGER,                    -- only set for one-time, when used
  PRIMARY KEY (kind, index_or_id)
);
```

Files locked at 0600. Backed up nightly via `hearthnet export` (encrypted with user passphrase).

---

## 6. Errors

`RatchetError` codes (M23-internal):
- `session_not_established`
- `decrypt_failed`
- `out_of_order_too_far`
- `message_too_old`
- `aad_mismatch`

Wire mapping per [CAP2 §9](../CAPABILITY_CONTRACT_v2.md):
- `e2e_session_missing` ← `session_not_established`
- `e2e_decrypt_failed` ← `decrypt_failed`, `aad_mismatch`
- `ratchet_out_of_order` ← `out_of_order_too_far`

---

## 7. Configuration

```python
config.e2e.enabled                       = True
config.e2e.chat_default_enabled          = True       # new 1:1 chats default to E2E
config.e2e.group_default_enabled         = True
config.e2e.file_default_enabled          = False      # opt-in per blob
config.e2e.prekey_refill_count           = E2E_PREKEY_BUNDLE_SIZE
config.e2e.rekey_after_messages          = E2E_RATCHET_REKEY_AFTER_MESSAGES
config.e2e.max_out_of_order              = E2E_RATCHET_MAX_OUT_OF_ORDER
```

---

## 8. Tests

### Unit
- `test_x25519_dh_symmetric`
- `test_x3dh_initiator_responder_agree`
- `test_ratchet_encrypt_decrypt_roundtrip`
- `test_ratchet_out_of_order_within_window`
- `test_ratchet_out_of_order_too_far_rejected`
- `test_rekey_after_n_messages`
- `test_group_sender_key_distribution_pairwise_only`
- `test_blob_envelope_recipient_only_can_decrypt`

### Integration
- `test_two_node_first_message_x3dh_session_persists`
- `test_session_recovery_after_disk_wipe`
- `test_group_add_member_can_decrypt_subsequent`
- `test_group_remove_member_cannot_decrypt_after_rotation`
- `test_file_envelope_2_recipients`

### Adversarial
- `test_replay_old_ratchet_message_rejected`
- `test_modified_ciphertext_decrypt_fails`
- `test_one_time_prekey_consumed_once`

---

## 9. Cross-references

| What | Where |
|------|-------|
| `e2e.*` events | [CAP2 §7](../CAPABILITY_CONTRACT_v2.md) |
| Encrypted chat body envelope | [CAP2 §1.1, §7.2 chat.message.sent](../CAPABILITY_CONTRACT_v2.md) |
| Chat service hook | [M10 ext](../../modules/M10-chat.md) — Phase 2 extension |
| Group chat | [M25](M25-group-chat.md) |
| File envelope use | [M07 ext](../../modules/M07-file-blobs.md) |
| Identity key conversion | [M01](../../modules/M01-identity.md) |

---

## 10. Open questions

1. **Post-quantum readiness.** X25519 + ChaCha20-Poly1305 is not PQ-safe. Hybrid (X25519 + ML-KEM-768) is Phase 3.
2. **Verification of session identity.** Signal does safety numbers; HearthNet can do the same. UI ergonomics deferred.
3. **Multi-device per identity.** If a user has anchor + mobile + laptop, do they share keys or have separate ones? Currently separate (each device is a separate NodeID; group threads include all of them). Could unify with a "linked devices" Phase 3 feature.
4. **Forward secrecy on group membership change.** Current spec asks members to rotate sender keys on removal. UX of forcing this needs design.
5. **Cryptographic auditing.** This module should be reviewed by a real cryptographer before going to civil-defence pilots. Listed in `THREAT_MODEL_v2.md`.
