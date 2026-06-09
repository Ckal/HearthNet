# M16 — Capability Tokens

**Spec version:** v1.0 (Phase 2)
**Depends on:** M01 (identity), X02 (events, for `auth.token.*`), X04 (config), X03 (observability)
**Depended on by:** M14 (federation), M15 (relay), M22 (mobile), M23 (optionally, for session credentials)

---

## 1. Responsibility

Issue, verify, and revoke short-lived **capability tokens** for delegation. A token says: "the holder of this token may invoke capability X (with these constraints) on behalf of issuer Y, until time Z."

Tokens are the mechanism Phase 2 uses for:
- Federation calls (a federated peer presents a token issued by an anchor of the peer community)
- Mobile clients (the mobile app presents a token issued during onboarding)
- Limited-scope sharing (e.g. "let this neighbour query our emergency corpus for the next hour")

Per-request Ed25519 signatures (Phase 1 §1.3) remain the default authentication; tokens are an *additional* mechanism.

---

## 2. File layout

```
hearthnet/identity/
└── tokens.py         # CapabilityToken, encode/decode, verify, revocation cache

hearthnet/services/auth/
├── __init__.py
└── service.py        # AuthService — registers auth.token.* capabilities
```

The token primitives live under `identity/` (low-level crypto). The capability handlers live as a normal service so they go through the bus.

---

## 3. Token envelope

Compact JWS-style. Compatible with off-the-shelf JWS decoders that accept `EdDSA`. Length budget: ≤ 800 bytes (fits a QR at error correction M).

### 3.1 Header

```json
{"alg": "EdDSA", "typ": "hntoken", "v": 1}
```

### 3.2 Payload

```json
{
  "iss":  "ed25519:<issuer NodeID full form>",
  "sub":  "ed25519:<subject NodeID full form>",
  "aud":  "ed25519:<audience community_id, optional>",
  "iat":  1717939200,
  "exp":  1717942800,
  "nbf":  1717939200,
  "jti":  "01HXR...",
  "scope": {
    "capabilities": ["rag.query@1.0", "embed.text@1.0"],
    "params_constraints": {
      "corpus": ["niederrhein-emergency"],
      "model":  ["bge-small-en-v1.5"]
    },
    "rate_limit_per_minute": 60,
    "max_calls_total":       null
  },
  "issued_via": "federation|onboarding|manual|relay"
}
```

`sub` MAY be `"*"` for a bearer-style token (anyone with the token may use it). Used sparingly — only for federation proxies where the actual subject is unknown at issuance time.

### 3.3 Signature

`Ed25519(base64url(header) + "." + base64url(payload))`. Final form:

```
hntoken://v1/<base64url(header)>.<base64url(payload)>.<base64url(signature)>
```

Total length: ~600–800 bytes typical.

---

## 4. Public API

### 4.1 `hearthnet/identity/tokens.py`

```python
# hearthnet/identity/tokens.py
from dataclasses import dataclass

@dataclass(frozen=True)
class TokenScope:
    capabilities:           list[str]               # e.g. ["rag.query@1.0"]
    params_constraints:     dict[str, list[str]]   # e.g. {"corpus": ["..."]}
    rate_limit_per_minute:  int
    max_calls_total:        int | None

@dataclass(frozen=True)
class CapabilityToken:
    """The fully decoded token, ready for verification."""
    issuer:       str
    subject:      str                                # "*" for bearer
    audience:     str | None
    issued_at:    int                                 # unix seconds
    expires_at:   int
    not_before:   int
    jti:          str                                 # ULID
    scope:        TokenScope
    issued_via:   str                                 # "federation"|"onboarding"|...
    signature:    bytes                               # raw 64 bytes

    @property
    def is_bearer(self) -> bool: ...

    def is_active(self, now: int | None = None) -> bool: ...

    def covers(self, capability_name: str, version: tuple[int, int],
               params: dict | None = None) -> bool:
        """True iff scope includes the capability and (if params_constraints set) every requested param value is in the allow-list."""

def issue_token(
    issuer_kp: KeyPair,
    subject: str,
    scope: TokenScope,
    *,
    ttl_seconds: int = TOKEN_DEFAULT_TTL_SECONDS,
    audience: str | None = None,
    issued_via: str = "manual",
    not_before_offset: int = 0,
) -> tuple[CapabilityToken, str]:
    """Build, sign, encode. Returns (token, encoded_str)."""

def encode_token(tok: CapabilityToken, header_signature: bytes) -> str:
    """Render to 'hntoken://v1/...'."""

def decode_token(text: str) -> CapabilityToken:
    """Parse + structural validation only. Does NOT verify the signature.
       Raises TokenError on malformed input."""

def verify_token(
    tok: CapabilityToken,
    *,
    expected_audience: str | None = None,
    revocation_cache: 'RevocationCache | None' = None,
    now: int | None = None,
    community_manifest: CommunityManifest,
) -> None:
    """Verify signature against issuer's pubkey, expiry, nbf, audience,
       revocation, and that the issuer is currently a community member
       (not revoked at the issuer's community level).
       Raises TokenError with specific code."""

class RevocationCache:
    """In-memory + persisted (SQLite) cache of revoked JTIs.
       Authoritative source is the event log."""

    def __init__(self, db_path: Path):
        ...

    def add(self, jti: str, revoked_at: int) -> None: ...
    def is_revoked(self, jti: str) -> bool: ...
    def hydrate_from_log(self, event_log: EventLog) -> int:
        """Read all auth.token.revoked events; bring cache up to date.
        Returns rows added."""

class TokenError(Exception):
    """code in {
       'token_invalid','token_expired','token_not_yet_valid',
       'token_signature_bad','token_audience_mismatch',
       'token_revoked','token_scope_insufficient',
       'token_issuer_revoked','token_malformed'}"""
    code: str
```

### 4.2 `hearthnet/services/auth/service.py`

```python
# hearthnet/services/auth/service.py
class AuthService:
    """Registers auth.token.issue / revoke / introspect capabilities."""

    name    = "auth"
    version = "1.0"

    def __init__(
        self,
        author_kp: KeyPair,
        event_log: EventLog,
        community_manifest_provider: Callable[[], CommunityManifest],
        revocation_cache: RevocationCache,
    ):
        ...

    def capabilities(self) -> list[tuple[CapabilityDescriptor, Callable, ParamsPredicate]]:
        """Registers: auth.token.issue@1.0, auth.token.revoke@1.0, auth.token.introspect@1.0."""

    async def start(self) -> None:
        """Hydrate the revocation cache from event log."""

    async def stop(self) -> None: ...
    def health(self) -> dict: ...

    # --- handlers ---

    async def handle_issue(self, req: RouteRequest) -> dict:
        """CAP2 §4.5. Build a CapabilityToken, sign with author_kp, emit auth.token.issued event."""

    async def handle_revoke(self, req: RouteRequest) -> dict:
        """CAP2 §4.6. Verify caller is issuer (or 'trusted'). Append auth.token.revoked event."""

    async def handle_introspect(self, req: RouteRequest) -> dict:
        """CAP2 §4.7. Self-only. Returns active status and scope."""
```

---

## 5. Behaviour

### 5.1 Token-bearer call lifecycle

```
caller hits any capability endpoint with:
  X-HearthNet-Token: hntoken://v1/...
  (and optionally X-HearthNet-Signature)
  ↓
X01 transport extracts and decodes
  ↓
verify_token(...) — signature, expiry, audience, revocation
  ↓
on success:
  caller_effective_identity = token.subject (or token.issuer if subject == "*")
  scope_check (does token cover this capability?)
  ↓
bus.handle_call() with the effective caller
  ↓
record token usage in metrics: hearthnet_token_calls_total{issuer, scope_match}
```

### 5.2 Co-existence with per-request signing

A request MAY carry both `X-HearthNet-Signature` and `X-HearthNet-Token`:

- Signature: proves *who* is making this exact call right now
- Token: proves they're *allowed* to (via delegation)

The token's `sub` MUST equal the signature's `From` NodeID, unless `sub == "*"`. Mismatch → `invalid_signature`.

This combination is the normal mode for federation: a federated peer's anchor signs with their key (signature) AND carries a token issued by their community's anchor delegating "rag.query is OK".

### 5.3 Issuance authority

A node may issue a token iff:

- The capabilities in scope are ones the issuer's community offers (or grants via federation)
- TTL ≤ `policy.capability_token_ttl_seconds` (community-wide policy bound)
- The issuer is a `member` (level ≥ member) of the community

The handler enforces these before signing.

### 5.4 Revocation

A token is revoked by appending `auth.token.revoked` to the event log:

- Issuer may revoke their own tokens
- A `trusted` member may revoke any token (operator override)
- The community root can revoke any token

Once the revoke event is in the log, all gossip-receiving nodes update their `RevocationCache`. Until that propagates, a revoked token may still be honoured briefly — design accepts up to 60 seconds of lag.

### 5.5 Bearer tokens (`sub == "*"`)

Used sparingly:

- Federation proxy tokens: peer community gets one bearer token to make federated calls; rotation every 24h
- Mobile push tokens (M22): one bearer token tied to a `PushDeviceID`, longer TTL

Bearer tokens trade convenience for less revocability granularity. The `jti` is still unique so a specific bearer can be killed.

### 5.6 Replay protection

Tokens are not single-use. Replay is mitigated by:
- Short TTL (default 1h)
- Audience binding (`aud` field): server rejects if `aud` ≠ ours
- Rate-limit budget (`scope.rate_limit_per_minute`)
- Revocation if abuse detected

For one-shot tokens (e.g. password-reset-style flows), set `max_calls_total: 1` and the server tracks usage via a per-jti counter.

### 5.7 Token-on-token (delegation chains)

Phase 2: **forbidden**. A token holder cannot issue new tokens. This avoids a delegation tree we cannot audit.

Phase 3 may add bounded delegation with a `delegates: int` counter.

---

## 6. Storage

### 6.1 Revocation cache table

```sql
CREATE TABLE IF NOT EXISTS token_revocations (
  jti          TEXT PRIMARY KEY,
  revoked_at   INTEGER NOT NULL,
  reason       TEXT,
  via_event_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_revocations_time ON token_revocations(revoked_at);
```

### 6.2 Rate-limit counters

Per-(jti, minute) sliding window in memory. Persisted only when capacity-exceeded events fire (for audit).

---

## 7. Errors

`TokenError` → wire mapping:

| TokenError code | Wire code | HTTP |
|-----------------|-----------|------|
| `token_malformed` | `bad_request` | 400 |
| `token_invalid` | `token_invalid` | 401 |
| `token_signature_bad` | `token_invalid` | 401 |
| `token_expired` | `token_expired` | 410 |
| `token_not_yet_valid` | `token_expired` | 410 |
| `token_audience_mismatch` | `unauthorized` | 401 |
| `token_revoked` | `token_revoked` | 401 |
| `token_scope_insufficient` | `token_scope_insufficient` | 403 |
| `token_issuer_revoked` | `revoked` | 403 |

---

## 8. Configuration

From [X04](../../cross-cutting/X04-config.md) (extension):

```python
config.auth.enabled                = True
config.auth.token_default_ttl_seconds = TOKEN_DEFAULT_TTL_SECONDS
config.auth.token_max_ttl_seconds  = TOKEN_MAX_TTL_SECONDS
config.auth.allow_bearer_tokens    = True
config.auth.federated_only_bearer  = True  # bearer tokens only issued for federation context
```

---

## 9. Tests

### Unit
- `test_token_encode_decode_roundtrip`
- `test_token_under_800_bytes`
- `test_token_signature_verified`
- `test_token_expired_rejected`
- `test_token_audience_mismatch_rejected`
- `test_token_scope_covers_exact_match`
- `test_token_scope_params_constraint_filtered`
- `test_revocation_event_updates_cache`
- `test_bearer_token_with_star_subject`

### Integration
- `test_federated_call_with_token_succeeds`
- `test_revoked_token_rejected_within_60_seconds`
- `test_rate_limit_per_token_enforced`
- `test_mobile_client_token_authenticates`

---

## 10. Cross-references

| What | Where |
|------|-------|
| Token wire format | [CAP2 §6.2](../CAPABILITY_CONTRACT_v2.md) |
| Token-bearer requests | [CAP2 §5.2](../CAPABILITY_CONTRACT_v2.md) |
| `auth.token.*` capabilities | [CAP2 §4.5–4.7](../CAPABILITY_CONTRACT_v2.md) |
| Used by federation | [M14 §5](M14-federation.md) |
| Used by relay tier | [M15 §4](M15-relay-tier.md) |
| Used by mobile client | [M22 §4](M22-mobile-native.md) |
| Phase 1 identity primitives | [M01](../../modules/M01-identity.md) |

---

## 11. Open questions

1. **Audience as community vs node** — Phase 2 uses community as audience. Should single-node audience be supported (one-call-to-one-node tokens)? Probably yes; adds `aud_kind: "community"|"node"`. Defer.
2. **JWE for confidential scope** — current scope is in cleartext. Some scope values are sensitive (corpus names). Wrap payload in JWE? Defer; out of scope MVP for tokens.
3. **Hardware-bound tokens** — Phase 3 idea: token bound to a TPM-attested device.
4. **Token-on-token (delegation)** — explicitly Phase 3.
