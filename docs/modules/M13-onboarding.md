# M13 — Onboarding

**Spec version:** v1.0
**Depends on:** M01 (identity), M08 (UI), X04 (config), X02 (events, to emit `community.*` events), `qrcode`, `Pillow`
**Depended on by:** First-run flow in `node.py`; entry point from M08 settings tab

---

## 1. Responsibility

The first time a user runs HearthNet, get them from "downloaded a binary" to "joined a community with a working node" in under two minutes. Specifically:

- Generate a device keypair if not present
- Offer two paths: **create** new community or **join** existing one
- Create flow: collect community name + policy, sign genesis manifest, display invite QR
- Join flow: scan / paste an invite, redeem it, emit `community.member.joined` event
- Optional: name the device, choose a profile (defaulted from hardware probe)

Out of scope:
- Federation between communities (Phase 2)
- Multiple-community membership on one device (Phase 2)

---

## 2. File layout

```
hearthnet/ui/
└── onboarding.py        # build_onboarding(), redeem_invite(), invite_to_qr()

hearthnet/identity/
└── manifest.py          # build_community_manifest() — reused
```

A standalone `hearthnet init` CLI command in [M12](M12-cli.md) shares the same primitives.

---

## 3. Public API

### 3.1 `onboarding.py`

```python
# hearthnet/ui/onboarding.py
from dataclasses import dataclass
import qrcode
from io import BytesIO

@dataclass(frozen=True)
class InviteBlob:
    """The thing that travels between devices to enable joining."""
    schema_version: int          # 1
    community_id:   str          # full
    community_name: str          # display
    inviter_node_id: str         # full
    invitee_node_id: str         # full of the device being invited
    initial_level:   str         # "member" | "trusted"
    bootstrap_endpoints: list[Endpoint]   # how to reach the inviter
    expires_at:     str
    signature:      str          # inviter's signature over canonical-JSON

# --- encoding ---

def encode_invite(blob: InviteBlob) -> str:
    """Compact representation suitable for QR / paste. Format:
    'hearthnet://v1/<base64-url-nopad of canonical-JSON>'.
    Aim: < 500 bytes (fits standard QR at error level M)."""

def decode_invite(text: str) -> InviteBlob:
    """Parse + verify signature. Raises OnboardingError on invalid."""

# --- QR ---

def invite_to_qr_png(blob: InviteBlob, *, box_size: int = 8) -> bytes:
    """Render the invite as a QR PNG. Used by UI for display."""

# --- create flow ---

def create_community(
    name: str,
    policy: CommunityPolicy,
    kp: KeyPair,
    state_dir: Path,
    event_log: EventLog,
) -> CommunityManifest:
    """1. Build genesis community manifest (root = kp).
    2. Persist manifest to <state_dir>/manifest.json.
    3. Append community.created event to event_log.
    4. Append community.member.invited + .joined for root device.
    Returns the manifest."""

# --- join flow ---

def make_invite(
    invitee_node_id_full: str,
    inviter_kp: KeyPair,
    community_manifest: CommunityManifest,
    bootstrap_endpoints: list[Endpoint],
    initial_level: str = "member",
    ttl_seconds: int = 86400,
) -> InviteBlob:
    """Create + sign an invite blob. Also emit a community.member.invited event."""

def redeem_invite(
    blob: InviteBlob,
    our_kp: KeyPair,
    transport_client: HttpClient,
    event_log: EventLog,
) -> CommunityManifest:
    """1. Verify the invite signature, expiry, that invitee_node_id matches us.
    2. Connect to one of bootstrap_endpoints; fetch /community/manifest.
    3. Verify the community manifest's signature chain (root key in invite matches).
    4. Run an initial X02 sync to populate the event log.
    5. Emit a community.member.joined event (our authorship) including our node manifest.
    6. Persist community manifest locally.
    Returns the manifest. Raises OnboardingError on failure."""

# --- UI builders (Gradio components) ---

def build_onboarding(config: Config, kp_provider: Callable[[], KeyPair]) -> 'gr.Blocks':
    """Standalone Blocks UI for the first-run flow. Two-step wizard:
       Step 1: 'Erstmal Schlüssel erzeugen' (auto, with progress)
       Step 2: choice — create or join
         - create: form (name, policy options) → preview manifest → confirm → show QR
         - join:   text area / camera upload for QR → preview invite → confirm → redeem
       Returns the assembled Blocks. node.py mounts this BEFORE the main UI when
       config.community.community_id is None."""

class OnboardingError(Exception):
    """code in {'invite_invalid','invite_expired','invitee_mismatch','bootstrap_unreachable',
              'community_manifest_invalid','sync_failed','already_member'}"""
    code: str
```

---

## 4. Flows in detail

### 4.1 Create-community flow

```
User clicks "Neue Community gründen"
  ↓
Form:
  • Community name (free text, 1..64 chars)
  • Allow new members to invite? (default true)
  • Minimum signatures to revoke a member: 3 (advanced)
  ↓
On submit:
  policy = CommunityPolicy(
      min_signatures_to_invite = 1,
      min_signatures_to_demote = 3,
      min_signatures_to_revoke = 3,
      capability_token_ttl_seconds = 86400,
      federation_enabled = True,
      default_member_can_invite = checkbox_value,
  )
  manifest = create_community(name, policy, our_kp, state_dir, event_log)
  config.community.community_id = manifest.community_id
  X04.save(config)
  ↓
"Du bist Gründer!" panel
  • Show community short id
  • Show your role: anchor
  • Show QR code for inviting first member (preconfigured invite to ANY device)
    → actually: show a "create invite" button that asks for the invitee's NodeID
  ↓
Continue → main UI
```

### 4.2 Join-community flow

```
User clicks "Einer Community beitreten"
  ↓
"Wie hast du die Einladung erhalten?"
  • Paste link / text
  • Upload QR image
  • Use camera (mobile only)
  ↓
decode_invite(text or scan) → InviteBlob
  • verify signature
  • check expiry
  • check invitee_node_id == our_node_id_full
  ↓
Preview:
  • Community name
  • Inviter display name (lookup via bootstrap_endpoints[0]/manifest)
  • Initial level: member
  • "Beitreten" button
  ↓
On confirm:
  redeem_invite(blob, our_kp, transport_client, event_log)
    → fetch community manifest from bootstrap
    → run X02 sync to fetch all history
    → emit community.member.joined event
    → persist community manifest
  config.community.community_id = blob.community_id
  X04.save(config)
  ↓
"Willkommen!" → main UI
```

### 4.3 Inviting someone (post-onboarding, from settings tab)

```
Settings → "Mitglied einladen"
  ↓
Two options:
  (a) Generate invite for a specific NodeID
       - user pastes invitee NodeID full form (they got it from their device)
       - or scans a "I'm a fresh device" QR shown on their screen
  (b) Use the in-person setup wizard (Phase 2: BLE pairing)
  ↓
make_invite(...) → InviteBlob
  • Emit community.member.invited event (so the rest of the community knows)
  • Display QR for the invitee to scan
  • Expires in 24h
```

### 4.4 "I'm a fresh device" QR

Before joining, a freshly-installed device displays a QR encoding only its `node_id_full` (no signature; this is a public key). The inviter scans this QR with their existing device to build an invite. Format:

```
hearthnet-id://v1/<base64-url-nopad of {"node_id_full": "...", "display_name": "Hannes' Tablet"}>
```

This is unsigned because nothing private is in it. The inviter is the source of trust.

---

## 5. Behaviour

### 5.1 First-run detection

`node.py` checks at startup:

```python
if config.community.community_id is None:
    # mount onboarding UI; don't start most services yet
    ...
else:
    # normal startup
```

After the user completes onboarding, `node.py` continues with the full startup sequence (now with a valid community).

### 5.2 Re-onboarding (changing community)

The settings tab has a "Leave community" action. After confirm, the local data for that community is moved to `<DATA>/communities/<id>.archived/` and the user is sent back to onboarding. The user keeps the same keypair unless they explicitly choose to regenerate it (which then makes a new identity).

### 5.3 What we sign and what we don't

| Artifact | Signed by | Why |
|----------|-----------|-----|
| Invite blob | Inviter | So invitee can prove this came from a member |
| Genesis community manifest | Founder (root) | Establishes the root of trust |
| `community.member.joined` event | The joining device | Asserts "I am here, with this manifest" |
| Fresh-device ID QR | Nobody | It's just a public key; sees + uses |

### 5.4 Failure modes during join

- Bootstrap endpoints unreachable → `bootstrap_unreachable` with retry option
- Invite expired → `invite_expired`, must request a new one
- Invitee mismatch → `invitee_mismatch` (someone tried to redeem someone else's invite)
- Already a member → `already_member`, no-op with a message

### 5.5 Privacy of invites

An invite contains:
- Community ID, name
- Inviter NodeID
- Invitee NodeID
- Bootstrap endpoints

It does **not** contain the event log. Anyone seeing an invite knows the community exists and who is who, but not what was said in it.

---

## 6. Errors

`OnboardingError` codes:

- `invite_invalid` — malformed or bad signature
- `invite_expired` — past TTL
- `invitee_mismatch` — invite addressed to a different NodeID
- `bootstrap_unreachable` — can't reach inviter for manifest fetch
- `community_manifest_invalid` — fetched manifest fails verification
- `sync_failed` — initial event-log sync failed
- `already_member` — we're already in this community

---

## 7. Configuration

No new config keys. Uses `config.identity.*` and `config.community.*` from [X04](../cross-cutting/X04-config.md).

---

## 8. Tests

### Unit
- `test_invite_encode_decode_roundtrip`
- `test_invite_qr_under_500_bytes`
- `test_invite_expired_rejected`
- `test_invite_addressed_to_someone_else_rejected`
- `test_create_community_emits_three_events` (created + invited self + joined self)
- `test_redeem_invite_results_in_joined_event`

### Integration
- `test_two_node_join_flow_end_to_end` — node A creates community, generates invite, node B redeems, both see each other as members
- `test_join_during_partial_partition` — bootstrap unreachable, retry succeeds
- `test_redeem_then_immediately_sync_marketplace` — historical posts visible after sync

---

## 9. Cross-references

| What | Where |
|------|-------|
| Community manifest schema | [CONTRACT §6.2](../CAPABILITY_CONTRACT.md) |
| `community.*` events | [CONTRACT §7.2](../CAPABILITY_CONTRACT.md) |
| Identity primitives | [M01](M01-identity.md) |
| UI integration | [M08 §8.5](M08-ui.md) |
| CLI `hearthnet init` | [M12 §3](M12-cli.md) |
| Event log + sync | [X02](../cross-cutting/X02-events.md) |

---

## 10. Open questions

1. **Multi-community membership** — out of scope MVP. Phase 2: same keypair, multiple `<DATA>/communities/<id>/` dirs.
2. **Recovery if device key lost** — currently impossible (key = identity). Phase 2: "social recovery" via 2-of-3 trusted members re-issuing a re-joined identity.
3. **BLE pairing** — Phase 2; faster than QR for adjacent devices.
4. **Camera capture on mobile web** — `getUserMedia` is available; needs HTTPS. Self-signed cert may trip browsers; document workaround.
