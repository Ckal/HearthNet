# M01 — Identity & Manifests

**Spec version:** v1.0
**Depends on:** X04 (config), PyNaCl, cryptography (for TLS cert generation)
**Depended on by:** X02 (events), X01 (transport), M02 (discovery), M03 (bus), and every service that signs anything

---

## 1. Responsibility

- Cryptographic identity (Ed25519 keypair) for one device
- Signing and verification of arbitrary canonical-JSON payloads
- Creation, signing, verification of **node manifests**
- Creation, signing, verification of **community manifests**
- Canonical JSON encoding (the one that signatures are computed over)
- TLS certificate generation (self-signed, pinned to the device key on first contact)
- Optional: capability tokens (Phase 2)

This module owns no event log — that is X02. It owns no networking — that is X01. It owns only crypto and document formats.

---

## 2. File layout

```
hearthnet/identity/
├── __init__.py         # re-exports
├── keys.py             # KeyPair, canonical_json, sign, verify, TLS cert
├── manifest.py         # NodeManifest, CommunityManifest, builders, verifiers
└── tokens.py           # Phase 2; stubs only in MVP
```

---

## 3. Public API

### 3.1 `keys.py`

```python
# hearthnet/identity/keys.py
from dataclasses import dataclass
from pathlib import Path
from typing import Any

NodeID    = str  # "ed25519:XXXX-XXXX-XXXX-XXXX" (short) or "ed25519:<base64-url-nopad>" (full)
Signature = str  # "ed25519:<base64-url-nopad>"

@dataclass(frozen=True)
class KeyPair:
    """Wraps Ed25519 signing key + verify key plus their string forms."""
    signing_key:    nacl.signing.SigningKey
    verify_key:     nacl.signing.VerifyKey
    node_id_full:   str          # "ed25519:<base64-url-nopad of 32 bytes>"
    node_id_short:  str          # "ed25519:XXXX-XXXX-XXXX-XXXX" (8 bytes, base32, 4-grouped)

    def sign(self, payload: dict) -> dict:
        """Return a new dict equal to payload with signature field added."""

    def sign_bytes(self, data: bytes) -> Signature:
        """Sign raw bytes; return 'ed25519:<base64-url-nopad>'."""

# --- generation / loading ---

def generate() -> KeyPair:
    """Create a fresh Ed25519 keypair (uses os.urandom)."""

def load(keys_dir: Path) -> KeyPair:
    """Load device.ed25519 + device.pub from keys_dir.
       Raises IdentityError('keys_missing') if not present,
       IdentityError('keys_invalid') if malformed.
       Validates permissions are 0600 on Unix."""

def load_or_generate(keys_dir: Path) -> KeyPair:
    """Load if present; otherwise generate and persist."""

def save(kp: KeyPair, keys_dir: Path) -> None:
    """Persist signing key as device.ed25519 (0600) and verify key as device.pub."""

# --- public-key handling ---

def short_node_id(verify_key_bytes: bytes) -> str:
    """First 8 bytes base32, grouped: 'ed25519:XXXX-XXXX-XXXX-XXXX'."""

def full_node_id(verify_key_bytes: bytes) -> str:
    """All 32 bytes, base64-url no pad, prefixed: 'ed25519:<b64>'."""

def parse_node_id(node_id: str) -> bytes:
    """Decode the full form back to 32 bytes. Short form raises ValueError."""

def verify_key_from_full(node_id_full: str) -> nacl.signing.VerifyKey:
    """Convenience: parse and wrap."""

# --- canonical JSON ---

def canonical_json(obj: Any) -> bytes:
    """Sorted keys, no whitespace, no trailing zeros on numbers, UTF-8.
       Used everywhere a signature is computed."""

# --- signing / verification ---

def sign_payload(payload: dict, kp: KeyPair) -> dict:
    """Add a 'signature' field over canonical_json(payload \\ {signature})."""

def verify_payload(payload: dict, vk: nacl.signing.VerifyKey) -> bool:
    """True iff the 'signature' field validates over canonical_json(payload \\ {signature})."""

def verify_payload_with_node_id(payload: dict, expected_node_id_full: str) -> bool:
    """Convenience: derive verify key from node_id and call verify_payload."""

# --- TLS ---

def generate_self_signed_cert(kp: KeyPair, host: str = "0.0.0.0") -> tuple[bytes, bytes]:
    """Generate an X.509 self-signed cert+key for TLS. The CN includes the short node id.
       Returns (cert_pem, key_pem). The cert is rotated when the device key changes (i.e. never)."""

class IdentityError(Exception):
    """code in {'keys_missing','keys_invalid','keys_permissions','bad_node_id','sign_failed','verify_failed'}"""
    code: str
```

### 3.2 `manifest.py`

```python
# hearthnet/identity/manifest.py
from dataclasses import dataclass, field
from typing import Any
from datetime import datetime, timezone, timedelta

# ---- types ----

@dataclass(frozen=True)
class Endpoint:
    transport: str                  # "https"
    host:      str
    port:      int

@dataclass(frozen=True)
class HardwareSpec:
    gpu:           str | None
    vram_gb:       float
    ram_gb:        float
    cpu_cores:     int
    disk_free_gb:  float

@dataclass(frozen=True)
class CapabilitySpec:
    """As it appears INSIDE a node manifest (subset of the full descriptor in M03)."""
    name:             str
    version:          str           # "1.0"
    stability:        str           # "stable" | "beta" | "experimental"
    schema_hash:      str           # "blake3:..."
    params:           dict[str, Any]
    max_concurrent:   int

@dataclass(frozen=True)
class NodeManifest:
    version:           int          # always 1 for this contract version
    contract_version:  str          # "1.0"
    node_id:           str          # full form
    display_name:      str
    community_id:      str
    profile:           str          # "anchor" | "hearth" | "spark" | "bridge"
    endpoints:         list[Endpoint]
    hardware:          HardwareSpec
    capabilities:      list[CapabilitySpec]
    uptime_seconds:    int
    load:              dict[str, Any]
    issued_at:         str          # RFC 3339
    expires_at:        str          # RFC 3339
    signature:         str

    def as_dict(self) -> dict: ...
    def is_expired(self, now: datetime | None = None) -> bool: ...

# ---- node manifest builder & verifier ----

def build_node_manifest(
    kp: KeyPair,
    community_id: str,
    display_name: str,
    profile: str,
    endpoints: list[Endpoint],
    hardware: HardwareSpec,
    capabilities: list[CapabilitySpec],
    uptime_seconds: int,
    load: dict[str, Any],
) -> NodeManifest:
    """Build and sign a fresh node manifest. issued_at = now,
       expires_at = now + MANIFEST_TTL_SECONDS."""

def parse_node_manifest(blob: bytes | dict) -> NodeManifest:
    """Parse JSON bytes or dict into a typed NodeManifest. Does NOT verify signature."""

def verify_node_manifest(manifest: NodeManifest, *, now: datetime | None = None) -> None:
    """Verify signature + expiry. Raises IdentityError on failure:
       'invalid_signature' | 'expired' | 'bad_manifest' (malformed structure)."""

# ---- community manifest ----

@dataclass(frozen=True)
class CommunityPolicy:
    min_signatures_to_invite:   int
    min_signatures_to_demote:   int
    min_signatures_to_revoke:   int
    capability_token_ttl_seconds: int
    federation_enabled:         bool
    default_member_can_invite:  bool

@dataclass(frozen=True)
class CommunityMember:
    node_id:   str
    level:     str         # "anchor" | "trusted" | "member"
    added_at:  str
    added_by:  str

@dataclass(frozen=True)
class RevokedEntry:
    node_id:    str
    revoked_at: str

@dataclass(frozen=True)
class CommunityManifest:
    version:               int
    community_id:          str
    name:                  str
    root_key:              str
    created_at:            str
    lamport_at_creation:   int
    policy:                CommunityPolicy
    members:               list[CommunityMember]
    revoked:               list[RevokedEntry]
    head_lamport:          int
    signature:             str

    def is_member(self, node_id: str) -> bool: ...
    def level_of(self, node_id: str) -> str | None: ...
    def is_revoked(self, node_id: str) -> bool: ...

def build_community_manifest(
    root_kp: KeyPair,
    name: str,
    policy: CommunityPolicy,
) -> CommunityManifest:
    """Build and sign the genesis community manifest. lamport_at_creation = 0, head_lamport = 0,
       members = [root as 'anchor'], revoked = []."""

def regenerate_community_manifest_from_state(
    materialised_state: dict,
    signing_kp: KeyPair,
) -> CommunityManifest:
    """Given a materialised view from the event log, produce a fresh signed manifest.
       Signing key may be any anchor's key, not just root."""

def parse_community_manifest(blob: bytes | dict) -> CommunityManifest: ...
def verify_community_manifest(cm: CommunityManifest) -> None: ...
```

### 3.3 `tokens.py` (Phase 2 — stubs only in MVP)

```python
# hearthnet/identity/tokens.py
@dataclass(frozen=True)
class CapabilityToken:
    issuer:     str             # NodeID issuing the token
    subject:    str             # NodeID who may use it
    capability: str             # "rag.query"
    issued_at:  str
    expires_at: str
    nonce:      str             # ULID
    signature:  str

def issue_token(...) -> CapabilityToken: ...     # Phase 2
def verify_token(token: CapabilityToken, expected_issuer: str) -> None: ...  # Phase 2
```

---

## 4. On-disk format

```
<DATA>/keys/
├── device.ed25519     # raw 32-byte signing key, no header, 0600
└── device.pub         # raw 32-byte verify key, 0644
```

Single-key design (no rotation, no chain). Rationale: a community member's key is their identity; rotation creates a new identity. If a key is compromised, the right action is to revoke that NodeID and the user re-onboards with a new key.

---

## 5. Behaviour

### 5.1 First-run flow

```
load_or_generate(keys_dir) →
  if device.ed25519 exists:
    read, validate permissions, parse → KeyPair
  else:
    generate → save → KeyPair
```

### 5.2 Manifest TTL and republish

The node orchestrator (`node.py`) republishes manifest every `MANIFEST_REPUBLISH_INTERVAL_SECONDS` (20s). Receivers consider any manifest with `expires_at < now` as `expired` and drop it.

### 5.3 Verification budget

Verification is cheap (Ed25519 is fast), but at scale (1000 events/sec) it can add up. Verifying nodes cache `(payload_hash, sig, result)` for 60 seconds to avoid re-verifying identical bytes.

### 5.4 Pinned keys

The first time we see a NodeID's verify key, we pin it in memory. A subsequent manifest with the same NodeID but a different verify key is rejected with `invalid_signature` and logged at `warning`. This is TOFU (trust-on-first-use) and is acceptable inside a community where invites carry the verify key.

---

## 6. Errors

All errors raise `IdentityError` with a `code` in: `keys_missing`, `keys_invalid`, `keys_permissions`, `bad_node_id`, `sign_failed`, `verify_failed`, `bad_manifest`, `expired`, `invalid_signature`.

These codes map cleanly onto the wire error codes in [CONTRACT §9](../CAPABILITY_CONTRACT.md).

---

## 7. Configuration

From [X04 §3](../cross-cutting/X04-config.md):

```python
config.identity.keys_dir       # where keys live
config.identity.auto_generate  # default True
```

---

## 8. Tests

### Unit
- `test_keypair_roundtrip` — save / load returns equal keys
- `test_short_node_id_format` — matches `ed25519:[A-Z2-7]{4}(-[A-Z2-7]{4}){3}`
- `test_canonical_json_is_stable` — sort + no-whitespace is deterministic
- `test_canonical_json_numbers` — `1.0`, `1.00`, `1` all canonicalise to `1`
- `test_sign_verify_roundtrip` — random payloads
- `test_verify_fails_on_modified_field` — flip one byte, verify returns False
- `test_node_manifest_expiry` — exact TTL boundary behaviour
- `test_community_manifest_genesis` — root key is sole anchor
- `test_tls_cert_includes_short_node_id` — CN match

### Integration
- `test_manifest_round_trip_over_http` — server emits, client receives, parses, verifies
- `test_tofu_key_pinning` — second different key for same NodeID is rejected

---

## 9. Cross-references

| What | Where |
|------|-------|
| Wire signing rules | [CONTRACT §1.3, §5.1](../CAPABILITY_CONTRACT.md) |
| Canonical JSON | [CONTRACT §1.2](../CAPABILITY_CONTRACT.md) |
| Node manifest schema | [CONTRACT §6.1](../CAPABILITY_CONTRACT.md) |
| Community manifest schema | [CONTRACT §6.2](../CAPABILITY_CONTRACT.md) |
| Used by event signing | [X02 §3](../cross-cutting/X02-events.md) |
| Used by transport TLS pinning | [X01 §4](../cross-cutting/X01-transport.md) |
| Used by bus per-request verification | [M03 §5.6](M03-bus.md) |

---

## 10. Open questions

1. **Mobile clients store keys in `localStorage`** — not great. Phase 2: WebCrypto + IndexedDB.
2. **Key rotation** — currently impossible without identity change. Phase 3 may add a "linked-keys" event.
3. **HSM / Yubikey support** — out of scope; possible Phase 3.
