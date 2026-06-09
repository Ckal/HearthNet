# M22 — Mobile Native Client

**Spec version:** v1.0 (Phase 2)
**Depends on:** M01 (identity), M15 (relay tier for push and NAT traversal), M16 (tokens for app auth), M23 (E2E for chat), X06 (WebSocket for live updates), the entire Phase 1 bus protocol as a wire client
**Depended on by:** end users on iOS/Android — first non-web HearthNet surface

---

## 1. Responsibility

Native mobile application that:

- Onboards into a community (scan invite QR or paste invite blob)
- Stores keys in the device's secure enclave (iOS Keychain, Android Keystore)
- Receives push notifications via the relay tier (M15)
- Calls the community's anchor(s) via the bus protocol over HTTP/SSE or WebSocket
- Provides UI for chat (1:1 + group), marketplace, ask (LLM), community feed
- Operates fully when the user's anchor is reachable; degrades gracefully when not

This module specifies **the contract between the mobile client and the rest of HearthNet**. The actual Flutter codebase lives in a separate repo (`/mobile-native`) and is not Python.

---

## 2. File layout

```
mobile-native/                          # separate Flutter project
├── pubspec.yaml
├── README.md
├── lib/
│   ├── main.dart
│   ├── onboarding/                     # invite scan, key gen
│   ├── identity/                       # key storage, signing
│   │   ├── secure_storage.dart
│   │   └── signing.dart
│   ├── bus/                            # protocol client
│   │   ├── http_client.dart
│   │   ├── ws_client.dart
│   │   └── sse_client.dart
│   ├── crypto/                         # E2E using cryptography_flutter / libsodium bindings
│   │   ├── x25519.dart
│   │   ├── ratchet.dart
│   │   └── envelope.dart
│   ├── push/                           # APNs / FCM hookup
│   │   └── subscriber.dart
│   ├── ui/                             # screens
│   │   ├── chat.dart
│   │   ├── marketplace.dart
│   │   ├── ask.dart
│   │   └── community.dart
│   └── settings/
├── ios/
├── android/
└── tests/

hearthnet/mobile/                        # Python-side helper (in the main package)
├── __init__.py
├── invite.py                            # mobile-targeted invite QR generation
└── push_authority.py                    # bus-side service for mobile push token registry
```

The Python `hearthnet/mobile/` package contains the anchor-side helpers used by the existing community. The Flutter code is its own world; this spec governs the wire contract it must implement.

---

## 3. Onboarding flow

```
User installs HearthNet app
  ↓
App: "Scan invite QR or paste invite link"
  ↓
On scan: parse hnvite:// blob (Phase 1 §13)
  ↓
App generates Ed25519 keypair via libsodium binding
  Persists private key in iOS Keychain (kSecAttrAccessibleAfterFirstUnlock)
  or Android Keystore (KeyProperties.AUTH_REQUIRED if biometric set)
  ↓
App calls bus.call("onboard.complete", input={
    "invite_token": "...",
    "node_id_full": "<our new ed25519 pub>",
    "device_class": "mobile",
    "display_name": "<user-entered>",
    "platform": "ios|android",
})
  ↓
Anchor processes invite (M13), emits node.joined event
  ↓
App fetches community manifest (signed); pins it
  ↓
App registers for push:
  - obtain APNs/FCM device token from OS
  - bus.call("relay.push.register", input={device_token, platform})
  ↓
App publishes E2E prekey bundle (e2e.prekeys.published event)
  ↓
Ready to use
```

---

## 4. Bus protocol on mobile

### 4.1 Same wire as desktop

The mobile client speaks the same HTTP/SSE/WebSocket protocol as Phase 1 anchors. It is a **client** that calls into anchors/services in its community; it does not host capabilities itself (mostly — see §4.4).

### 4.2 Endpoint selection

The mobile client maintains an ordered list of endpoints:

1. **Cached anchor endpoints** from last successful manifest fetch
2. **Local network discovery** (mDNS via [Bonjour iOS / NSD Android]) — only when on Wi-Fi
3. **Relay tier** (M15) — for NAT traversal when on cellular
4. **DHT lookup** (X05) — last resort

Per call, the client tries endpoints in order; first success wins. Persistent failures bubble up as `relay_unreachable` or `network_unreachable`.

### 4.3 Reconnection

WebSocket connections are persistent for tool-call loops and live pubsub. On disconnect, the client reconnects with exponential backoff (1s, 2s, 4s, ..., capped at 60s). Reconnect re-subscribes to all active topics.

### 4.4 Mobile-as-callable

In Phase 2, the mobile client does NOT register capabilities back into the community. It's purely a caller. Phase 3 may allow simple things (`market.list` from local cache while offline).

### 4.5 Token-bearer mode

For background-fetch (when the app is suspended), the OS may run a brief task. Background tasks use a **bearer token** from M16 (issued at onboarding, refreshed on each app foreground). The token has scope:

```json
{
  "capabilities": ["chat.fetch","marketplace.list"],
  "rate_limit_per_minute": 30
}
```

This avoids needing the user's biometric to unlock the private key for background polling.

---

## 5. Push notifications

### 5.1 What triggers a push

When the following events occur in the community, anchors send a push to relevant subscribed mobile devices:

- `chat.message.sent` where recipient is the mobile user
- `chat.thread.message.sent` where mobile user is a thread member
- `marketplace.post.created` where post matches user's subscribed categories
- `community.alert` (broadcast emergency alert)
- `node.joined` (subscribed users only)

### 5.2 Push payload shape

Per [M15 §5.4](M15-relay-tier.md), the payload is minimal:

```json
{
  "event_type": "chat.message.sent",
  "sender_short": "7H4G-...",
  "preview": "Hallo Jana, ich bring..."     // optional cleartext preview if not E2E
}
```

For E2E messages, the preview is absent and the app must fetch + decrypt on open.

### 5.3 iOS vs Android specifics

**iOS:** APNs payload with `aps.alert.title` and `aps.alert.body`. Background mode enabled to fetch on receive (`content-available: 1`).

**Android:** FCM `data` message (not `notification` — we control display). Handled by the app's `FirebaseMessagingService`.

### 5.4 Quiet hours

User-configurable. Push silenced 22:00–07:00 by default; emergency alerts override.

### 5.5 Mute and per-thread settings

Per-thread mute, per-category marketplace silence. Stored in `mobile.preferences` event (self-only, encrypted-at-rest on device).

---

## 6. Secure key storage

### 6.1 iOS — Keychain Services

```dart
// lib/identity/secure_storage.dart (sketch)
const _accessibility = 'kSecAttrAccessibleAfterFirstUnlock';

Future<void> storePrivateKey(String label, Uint8List bytes) async {
  await KeychainAccess.setData(
    label: label,
    data: bytes,
    accessibility: _accessibility,
    accessControl: AccessControl.userPresence,  // biometric on key use
  );
}
```

### 6.2 Android — Keystore

Hardware-backed if available (StrongBox on modern Pixels), else TEE.

```dart
final cipher = await CryptographyFlutter.aesGcm(
  keyId: 'hearthnet_identity_v1',
  requireAuth: AuthMethod.biometric,
);
```

### 6.3 Backup

Private keys are NEVER backed up via iCloud / Google Backup. App-level backup uses an encrypted export blob (user-chosen passphrase) that the user is expected to save out-of-band (e.g. password manager, written down).

`config.mobile.cloud_backup_allowed = false` enforced.

### 6.4 Lost device

If the user loses the device, they:

1. Wait out the device's session — eventually messages stop delivering
2. From another device, call `node.revoke` on this NodeID (anchor co-signs)
3. The revoked NodeID is then blacklisted; the lost phone, even if recovered, can't authenticate

This is identical to the Phase 1 node revocation flow.

---

## 7. UI surface (mobile)

Mirrors the web UI ([M08](../../modules/M08-ui.md)) but native:

| Tab | Content |
|-----|---------|
| **Chat** | 1:1 conversations + group threads. Live updates via WS. Voice notes optional (record → STT → send transcript + audio attachment). |
| **Market** | List + post; image attachments via camera/gallery. |
| **Ask** | LLM chat. Tool-augmented mode available. Voice input button. |
| **Community** | Member list, recent events, federation peers. |
| **Settings** | Push prefs, language, backup, advanced. |

All UI is plain Material/Cupertino — no exotic frameworks. Matches Christof's preference for boring, durable tech.

---

## 8. Configuration

Mobile-side (lives in app):

```dart
const config = {
  'community_id': '<from invite>',
  'anchor_endpoints': [/* from manifest */],
  'relay_url': 'https://relay.hearthnet.de',
  'push_enabled': true,
  'quiet_hours': {'start': '22:00', 'end': '07:00'},
  'background_fetch_minutes': 15,
};
```

Anchor-side (Python, for the push_authority service):

```python
config.mobile.push_enabled              = True
config.mobile.push_categories_marketplace = ["essentials","emergency"]
config.mobile.push_quiet_hours_default  = ("22:00","07:00")
```

---

## 9. Errors

| Condition | UI presentation |
|-----------|-----------------|
| No network | Offline banner; queued sends |
| Anchor unreachable | "Your community anchor is offline. Retrying..." |
| Relay unreachable | Falls back to direct; warns if all fail |
| Token expired | Silent refresh; only surface if refresh fails |
| Push delivery failed | No UI; logged for diagnostics |
| Manifest signature mismatch | Hard block; re-onboard required |

---

## 10. Tests

### Flutter side
- Widget tests for each tab
- Integration test for onboarding flow with a mock anchor
- E2E test using a real anchor in CI (Linux runner running hearthnet)

### Anchor-side Python
- `test_push_subscription_recorded`
- `test_push_dispatch_on_chat_message_sent`
- `test_quiet_hours_silences_non_emergency`
- `test_revocation_revokes_mobile_session`

### Manual
- iOS + Android smoke tests on physical devices
- Background-fetch verified across 30-minute suspensions

---

## 11. Cross-references

| What | Where |
|------|-------|
| Bus protocol | [Phase 1 CAP §5](../../CAPABILITY_CONTRACT.md) |
| Push relay tier | [M15 §5.4](M15-relay-tier.md) |
| Token-bearer auth | [M16 §5.5](M16-tokens.md) |
| E2E chat | [M23](M23-e2e-encryption.md) |
| WebSocket | [X06](../cross-cutting/X06-websocket.md) |
| Invite blobs | [Phase 1 CAP §13](../../CAPABILITY_CONTRACT.md) |
| Web UI (mirror) | [M08](../../modules/M08-ui.md) |

---

## 12. Open questions

1. **Flutter vs React Native vs native (Swift + Kotlin).** Choosing Flutter for shared codebase and Christof's stated preference for boring/durable stacks. Reconsider if Flutter's keychain support is shaky.
2. **End-to-end encryption library in Flutter.** Need a libsodium binding that matches the Python side bit-exactly. `flutter_sodium` is well-maintained; verify on both platforms.
3. **Background fetch reliability.** iOS throttles aggressively. We accept "best effort"; push is the real delivery mechanism.
4. **Offline mode depth.** Mobile-only LLM (small Phi-3 / Gemma 2B) is Phase 3.
5. **Web push for PWA.** Could the same flow target a PWA (no native app)? Yes, with FCM web push; documented but not built in Phase 2.
6. **Family-share licence.** Christof might want to ship the iOS app to family members under his account; App Store policy permits this within Family Sharing.
