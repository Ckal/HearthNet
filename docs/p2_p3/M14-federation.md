# M14 — Federation

**Spec version:** v1.0 (Phase 2)
**Depends on:** M01 (identity), M16 (tokens), X02 (events), X05 (DHT, for cross-LAN bootstrap), X01 (transport), M03 (bus), M15 (relay, for NAT traversal)
**Depended on by:** M22 (mobile uses federation for cross-community discovery), all services indirectly (federated calls route through M14)

---

## 1. Responsibility

Let two **communities** establish a trust link and grant each other scoped access to specific capabilities. Federation is the bridge from "your house" to "the neighbourhood".

- Establish a federation between two communities (mutual cross-signature)
- Enforce scope on cross-community capability calls
- Route federated calls through a designated **Bridge** node profile
- Heartbeat between federated communities so liveness is visible
- Issue federation tokens (via M16) for individual calls

Out of scope:
- Many-community mesh federation — Phase 3 (this module handles bilateral only)
- Anonymous federation — never

---

## 2. File layout

```
hearthnet/federation/
├── __init__.py
├── manifest.py         # FederationManifest builder + verifier
├── peering.py          # the cross-sig handshake
├── relay_client.py     # outbound calls into peer community
└── service.py          # FederationService — registers federation.* capabilities
```

---

## 3. Federation manifest

Format defined in [CAP2 §6.1](../CAPABILITY_CONTRACT_v2.md). Key properties:

- Lives in **both** communities' event logs
- Signed by anchors of both, with per-community `min_signatures_to_federate` co-signatures
- Carries the **scope** each side grants the other
- Has an expiry (`expires_at`) — typically 1 year, with auto-renewal via heartbeats

A node may belong to **one** community (Phase 1) and that community may be federated with **N** other communities. Federation is a community-level relationship, not per-node.

---

## 4. Public API

### 4.1 `manifest.py`

```python
# hearthnet/federation/manifest.py
from dataclasses import dataclass

@dataclass(frozen=True)
class FederationScope:
    """What one community grants the other."""
    capabilities:        list[str]                   # ["rag.query@1.0"]
    params_constraints:  dict[str, list[str]]         # {"corpus":["public-emergency"]}
    rate_limit_per_minute: int                        # cross-community budget
    data_visibility:     str                          # "public_corpora_only"|"members_only"|"open"

@dataclass(frozen=True)
class FederationManifest:
    schema_version:  int
    federation_id:   str
    community_a:     str
    community_b:     str
    established_at:  str
    expires_at:      str
    scope_a_to_b:    FederationScope                  # what A grants B
    scope_b_to_a:    FederationScope                  # what B grants A
    bootstrap_endpoints_a: list[Endpoint]
    bootstrap_endpoints_b: list[Endpoint]
    signature_a:     dict                              # {signed_by, signature, co_signers}
    signature_b:     dict

    def grants_to(self, calling_community_id: str) -> FederationScope | None:
        """Returns the scope grant *to* the calling community (if federated, else None)."""

    def is_expired(self, now: datetime | None = None) -> bool: ...

def build_federation_proposal(
    our_community_manifest: CommunityManifest,
    peer_community_manifest_url: str,
    proposed_scope_to_grant: FederationScope,
    proposed_scope_to_receive: FederationScope,
    bootstrap_endpoints: list[Endpoint],
) -> 'FederationProposal':
    """Step 1: prepare a proposal. Not yet a manifest — just a draft for the other side."""

@dataclass(frozen=True)
class FederationProposal:
    community_a:           str
    community_b:           str
    scope_a_to_b:          FederationScope
    scope_b_to_a:          FederationScope
    bootstrap_endpoints_a: list[Endpoint]
    bootstrap_endpoints_b: list[Endpoint]
    proposer_signature:    str

def co_sign_federation(
    proposal: FederationProposal,
    signing_kp: KeyPair,
    role: str,                 # "a" or "b"
) -> dict:
    """Returns {signed_by, signature, co_signers[]} payload."""

def finalize_federation_manifest(
    proposal: FederationProposal,
    sig_a: dict,
    sig_b: dict,
) -> FederationManifest:
    """Assemble fully-signed manifest after both sides have signed."""

def parse_federation_manifest(blob: bytes | dict) -> FederationManifest: ...
def verify_federation_manifest(
    m: FederationManifest,
    community_a_manifest: CommunityManifest,
    community_b_manifest: CommunityManifest,
) -> None:
    """Verify both sides signed, anchors are valid in their communities,
    co-signer counts meet policy, expiry is in the future."""
```

### 4.2 `peering.py`

```python
# hearthnet/federation/peering.py
class FederationHandshake:
    """Conducts the multi-step cross-signing handshake.
       Stateful; one instance per active proposal."""

    def __init__(
        self,
        our_community_manifest: CommunityManifest,
        our_kp: KeyPair,
        transport_client: HttpClient,
        event_log: EventLog,
    ):
        ...

    async def initiate(
        self,
        peer_endpoints: list[Endpoint],
        scope_to_grant: FederationScope,
        scope_to_receive: FederationScope,
    ) -> FederationProposal:
        """1. Fetch peer's community manifest.
        2. Build proposal.
        3. Sign as community A's anchor.
        4. POST to peer.
        5. Receive peer's signed proposal back.
        6. Verify both signatures and gather more local co-signers if policy requires.
        Returns the fully-signed proposal ready to finalize."""

    async def accept(self, proposal: FederationProposal) -> FederationManifest:
        """The other side accepting an incoming proposal.
        Returns the finalized manifest (publishable to event log)."""

    async def publish(self, manifest: FederationManifest) -> None:
        """Append federation.peer.added event to local log.
        Push the manifest to peer so they can do the same."""
```

### 4.3 `relay_client.py`

```python
# hearthnet/federation/relay_client.py
class FederationCaller:
    """Outbound side: makes calls into federated communities.
       Used by services when their request triggers a federated lookup
       (e.g. rag.query across federated corpora)."""

    def __init__(
        self,
        bus: CapabilityBus,
        our_kp: KeyPair,
        our_community_id: str,
        federation_manifests_provider: Callable[[], list[FederationManifest]],
    ):
        ...

    async def call_in_peer(
        self,
        peer_community_id: str,
        capability: str,
        version: Version,
        body: dict,
        *,
        timeout_seconds: float | None = None,
    ) -> dict:
        """1. Look up federation manifest for peer_community_id.
        2. Verify scope includes (capability, params).
        3. Issue an auth.token via local M16 with capability scope.
        4. Pick a peer Bridge endpoint (from manifest.bootstrap_endpoints_b).
        5. POST /bus/v1/call to peer's federation.proxy@1.0 with token + body.
        Returns the result. Raises FederationError on scope/auth issues."""

    async def stream_in_peer(...) -> AsyncIterator[Frame]:
        """Streaming variant."""
```

### 4.4 `service.py`

```python
# hearthnet/federation/service.py
class FederationService:
    name    = "federation"
    version = "1.0"

    def __init__(
        self,
        bus: CapabilityBus,
        event_log: EventLog,
        replay_engine: ReplayEngine,
        author_kp: KeyPair,
        community_manifest_provider: Callable[[], CommunityManifest],
        revocation_cache: RevocationCache,
    ):
        ...

    def capabilities(self) -> list[tuple[CapabilityDescriptor, Callable, ParamsPredicate]]:
        """Registers: federation.peer.add, federation.peer.remove,
        federation.peer.list, federation.proxy (all @1.0)."""

    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    def health(self) -> dict: ...

    # --- handlers ---

    async def handle_peer_add(self, req: RouteRequest) -> dict:
        """CAP2 §4.1. Run handshake; check co-signatures; emit event."""

    async def handle_peer_remove(self, req: RouteRequest) -> dict:
        """CAP2 §4.2."""

    async def handle_peer_list(self, req: RouteRequest) -> dict:
        """CAP2 §4.3."""

    async def handle_proxy(self, req: RouteRequest) -> dict | AsyncIterator[dict]:
        """CAP2 §4.4. Forward a federated call to the local bus.
        1. Verify token attached to request.
        2. Look up federation manifest, check scope.
        3. Call bus.call(target_capability, version, body) internally.
        4. Return result (or stream frames)."""

    # --- maintenance ---

    async def heartbeat_loop(self) -> None:
        """Per FEDERATION_HEARTBEAT_SECONDS, ping each federated peer's
        federation.peer.list. Update last_heartbeat. Emit
        federation.heartbeat event."""
```

---

## 5. Behaviour

### 5.1 Two-phase handshake

```
Community A's anchor decides to federate with B.
  ↓
A: peering.initiate(B_endpoints, scope_a_to_b, scope_b_to_a)
   → fetch B's community manifest
   → build proposal; sign as A
   → POST /federation/proposal to B's bridge
   ↓
B receives proposal, presents to a trusted member.
  human decision (or auto-policy)
   ↓
B: peering.accept(proposal)
   → sign as B
   → return signed proposal
   ↓
A: gather more local co-signers if our policy.min_signatures_to_federate > 1
   ↓
A: finalize_federation_manifest(proposal, sig_a, sig_b)
   ↓
A: publish federation.peer.added event locally
   ↓
A: POST manifest to B so they publish too
   ↓
both communities heartbeat each other periodically
```

### 5.2 Bridge node profile

A community designates one or more nodes with `profile: "bridge"`. Bridge nodes:

- Always-on (best-effort)
- Have a publicly-reachable endpoint or a relay-tier (M15) registration
- Run `FederationService` and act as the proxy for inbound federated calls
- Hold the bandwidth budget for cross-community traffic

Non-bridge nodes can still **call into** federated communities (via M14 `FederationCaller`); they just don't *serve* cross-community calls.

### 5.3 Scope enforcement (inbound)

When `federation.proxy` is invoked:

1. Caller signature verified (Phase 1 §1.3)
2. Caller's community is parsed from token's `iss`
3. Federation manifest lookup; absent → `not_federated`
4. Scope check: `(capability, version)` ∈ scope and params allowed → else `federation_forbidden`
5. Token's signature verified against issuer's community anchors
6. Token's `aud` must match our community
7. Token's `scope` ⊆ federation manifest's scope (caller's community can't grant themselves more than they were granted)
8. Dispatch internally via bus
9. Record metrics: `hearthnet_federation_calls_total{peer_community, capability, result}`

### 5.4 Heartbeats and expiry

- Every `FEDERATION_HEARTBEAT_SECONDS` (300), each bridge calls `federation.peer.list` on each federated peer
- If a heartbeat fails 3 times in a row, the peer is marked `degraded` in the local view
- Federation manifests have `expires_at`. 30 days before expiry, a renewal handshake is auto-initiated. If renewal fails by expiry, the federation lapses; calls return `not_federated`.

### 5.5 Revocation

To break a federation:

- Either side may call `federation.peer.remove`
- Co-signature requirements: same as creation (`policy.min_signatures_to_federate`)
- Event `federation.peer.removed` is published locally; peer is notified and publishes their own
- All outstanding tokens issued under this federation are implicitly revoked (M16 verifies federation still exists)

### 5.6 Identity import (Phase 2.5 hook)

A federated user with NodeID in community A wishing to access community B's services *as themselves* (not via their community A anchor's token) can use `federation.identity.attest` (reserved capability, Phase 2.5). Out of scope for first cut.

### 5.7 Trust transitivity

**Not transitive.** A↔B and B↔C do not imply A↔C. Each pair establishes its own manifest. This is intentional — explicit consent.

### 5.8 Conflict: federation with revoked member's community

If community A has federated with B, and later A's anchor (the signer) is revoked from A:

- The federation manifest's signature *was* valid at sign time
- Going forward, A's community may renew with a new anchor signature
- B verifies federation against A's current anchor set on every call — if no current anchor co-signs, the federation is invalid

---

## 6. Discovery integration

A community wishing to find a federated peer they haven't talked to in a while:

1. Look up `bootstrap_endpoints` in their stored federation manifest
2. Try each; if all fail, fall back to [X05 DHT](../cross-cutting/X05-dht.md): `find_value(blake3(peer_community_id))`
3. If DHT also returns nothing, try [M15 relay](M15-relay-tier.md): `relay.lookup_community(peer_community_id)`
4. Only after all three fail → mark federation as `unreachable`; UI shows offline indicator

---

## 7. Errors

`FederationError`:

- `not_federated` — no manifest for this peer
- `federation_expired` — manifest past expires_at
- `scope_violation` — request outside granted scope
- `bridge_unreachable` — couldn't reach any of peer's bridges
- `co_signer_insufficient` — proposal lacks required signature count
- `peer_community_invalid` — peer's manifest failed verification

Wire mapping per [CAP2 §9](../CAPABILITY_CONTRACT_v2.md).

---

## 8. Configuration

```python
config.federation.enabled              = False           # opt-in
config.federation.bridge_node          = False           # we serve cross-community calls
config.federation.relay_url            = None            # M15 hosted relay for NAT
config.federation.auto_renew_days_before = 30
config.federation.max_peer_communities = 16
config.federation.heartbeat_seconds    = FEDERATION_HEARTBEAT_SECONDS
config.federation.scope_default_rate_limit_per_minute = 60
```

Constants: `FEDERATION_MANIFEST_TTL_SECONDS`, `FEDERATION_HEARTBEAT_SECONDS`.

---

## 9. Tests

### Unit
- `test_federation_proposal_builds_correctly`
- `test_co_sign_signature_verifies`
- `test_finalize_requires_min_signers`
- `test_grants_to_returns_scope_for_correct_direction`
- `test_expired_federation_rejects_calls`

### Integration
- `test_two_community_federation_round_trip` — A and B in different processes federate, then A queries B's RAG via proxy
- `test_scope_violation_returns_403`
- `test_heartbeat_marks_degraded_after_3_failures`
- `test_revocation_breaks_existing_tokens`
- `test_renewal_30_days_before_expiry`

### Chaos
- `test_partition_during_federation_handshake_resumable`

---

## 10. Cross-references

| What | Where |
|------|-------|
| Federation manifest schema | [CAP2 §6.1](../CAPABILITY_CONTRACT_v2.md) |
| `federation.*` capabilities | [CAP2 §4.1–4.4](../CAPABILITY_CONTRACT_v2.md) |
| Token issuance for cross-community | [M16 §5.1](M16-tokens.md) |
| DHT bootstrap | [X05 §4.3](../cross-cutting/X05-dht.md) |
| Relay tier NAT traversal | [M15](M15-relay-tier.md) |
| Bridge node profile | [Phase 1 PRD §5.4 + this module §5.2](../../HEARTHNET_PRD_v2.md) |
| Phase 3 transitive federation | TBD |

---

## 11. Open questions

1. **Multi-party federation (mesh of N>2 communities)** — currently bilateral only. Phase 3 candidate.
2. **Federated marketplace** — should `market.list` cross federations? Reserved scope param; default off.
3. **Federated identity** — single-sign-on across federated communities. Phase 2.5; design depends on token-on-token.
4. **Federation revocation event propagation** — if A↔B and A↔C, and B unilaterally revokes A, should C see this? MVP: no, each pair is independent.
5. **Audit log for federation activity** — should there be a separate "federation_audit" log so cross-community activity is easy to surface to operators? Yes, Phase 2.5.
