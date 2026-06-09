# M31 — Civil Defense (NRW Bevölkerungsschutz Pilot)

**Spec version:** v3.0 — *experimental*
**Depends on:** [M03 Capability Bus](../../modules/M03-capability-bus.md), [X02 Event Log](../../cross-cutting/X02-events.md), [M01 Identity](../../modules/M01-identity.md), [M11 Notifications](../../modules/M11-notifications.md), [M14 Federation](../../phase-2/modules/M14-federation.md), [M16 Tokens](../../phase-2/modules/M16-tokens.md), [M30 Evidence](./M30-evidence-ebkh.md), [M29 LoRa Beacons](./M29-lora-beacons.md), [M22 Mobile Native](../../phase-2/modules/M22-mobile-native.md)
**Depended on by:** nothing — terminal module; civil defense is a downstream consumer of everything else

---

## 1. Responsibility

A scoped pilot for **NRW Bevölkerungsschutz**: integrate HearthNet with the role structures that Germany's civil-defence ecosystem actually uses (THW, DRK, Feuerwehr, Katastrophenschutz) so that during an incident, role-certified members can publish authenticated alerts, coordinate locally, and produce a tamper-evident audit trail that survives legal review.

This module is deliberately **regional and regulated**. It does *not* try to be a global civil-defence platform. It encodes the role taxonomy, certificate semantics, and audit-retention rules that apply in Nordrhein-Westfalen, with hooks for other German Länder and EU regions to plug in later. The pilot lives in Issum and the Niederrhein because that's where Christof can actually walk into a Feuerwehrhaus and get this tested with humans who will use it under stress.

Where the rest of HearthNet aims for "soft consensus across neighbours", this module aims for "hard provenance, signed by an authority, retained per legal mandate". Different ergonomics. Different threat model.

---

## 2. Non-goals

- **Replacing official alert systems.** NINA, KATWARN, Cell-Broadcast, and BOS radio remain the authoritative channels. M31 is *complementary* — it works when official channels are degraded, congested, or geographically miss the affected area, and it carries the *local context* that mass-broadcast systems can't.
- **Issuing legally binding evacuation orders.** Those come from the Krisenstab and are out of any AI-mediated system's authority.
- **Modelling every German Land.** v3.0 targets NRW; M31 has a region adapter so others can be added, but the module ships with NRW only.
- **Replacing TETRA-BOS.** Professional emergency-services radio is its own thing. We coexist; we don't interop.
- **Automatic identity verification of certificate holders.** A role certificate carries who issued it and who it was issued to. *Verifying* that a holder is who they claim is the issuer's responsibility, not ours. We check the signature chain; we don't re-do the background check.
- **Persistent geolocation of helpers.** We record where alerts target and where reported incidents are. We do not continuously track helpers' phones.

---

## 3. File layout

```
hearthnet/civdef/
├── __init__.py
├── service.py             # CivilDefenseService — capability handler
├── alert.py               # Alert, AlertEnvelope, AlertSeverity dataclasses
├── role.py                # RoleCertificate, role schemas per region
├── audit.py               # Tamper-evident audit chain + export
├── regions/
│   ├── __init__.py
│   ├── nrw.py             # NRW role taxonomy & issuer trust roots
│   └── _stubs.py          # other Länder placeholders
├── target.py              # Geographic / role / channel targeting
└── ack.py                 # Acknowledgement collection
```

---

## 4. Public API

### 4.1 Dataclasses

```python
AlertID = NewType("AlertID", str)            # ULID
AlertSeverity = Literal["info","advisory","warning","emergency","extreme"]

@dataclass(frozen=True)
class RoleCertificate:
    cert_id:         str
    holder:          NodeID
    role:            str                       # canonical role, e.g. "DE.NRW.THW.OV.Leiter"
    region:          str                       # "DE.NRW.KreisKleve"
    issuer:          NodeID                    # issuing authority's HearthNet identity
    issuer_chain:    tuple[NodeID, ...]        # chain back to a trust root
    issued_at:       datetime
    expires_at:      datetime
    scopes:          frozenset[str]            # what this cert is allowed to do
    signature:       bytes
    revocation_url:  str | None

@dataclass(frozen=True)
class AlertTarget:
    region:          str                       # "DE.NRW.KreisKleve.Issum"
    bbox:            Bbox | None               # optional precise geo target
    roles:           tuple[str, ...]           # which roles should see this; empty = public
    channels:        tuple[Literal["push","lora","federation","local"], ...]

@dataclass(frozen=True)
class Alert:
    alert_id:        AlertID
    severity:        AlertSeverity
    title:           str                       # ≤ 80 chars
    body:            str                       # ≤ 1000 chars
    target:          AlertTarget
    instructions:    tuple[str, ...]           # short imperative lines
    published_at:    datetime
    expires_at:      datetime
    publisher:       NodeID
    publisher_role:  str
    publisher_cert:  str                       # cert_id
    evidence_claim:  ClaimID | None            # link to M30 claim chain if relevant
    correlation_id:  str | None                # links to NINA/KATWARN ID if mirrored
    signature:       bytes                     # publisher signs the alert
    issuer_attestation: bytes | None           # optional co-sign by a higher-tier issuer

@dataclass(frozen=True)
class AlertEnvelope:
    alert:           Alert
    federation_hops: tuple[NodeID, ...]        # forward path for audit
    received_at:     datetime
    received_via:    Literal["bus","federation","lora_signal","manual"]

@dataclass(frozen=True)
class Ack:
    alert_id:        AlertID
    acker:           NodeID
    acked_at:        datetime
    status:          Literal["received","acting","need_help","standing_down","mistaken"]
    note:            str                       # ≤ 280 chars
    signature:       bytes

@dataclass(frozen=True)
class AuditEntry:
    seq:             int                       # monotonic per audit chain
    alert_id:        AlertID
    event:           str                       # "published","forwarded","acked","mirrored","cancelled"
    actor:           NodeID
    at:              datetime
    payload_sha:     str
    prev_sha:        str                       # chain-link to previous audit entry
    signature:       bytes
```

### 4.2 Capabilities

All under `experimental.civdef.*`:

```python
async def civdef_alert_publish(draft: AlertDraft) -> AlertID
async def civdef_alert_cancel(alert_id: AlertID, reason: str) -> CancelReceipt
async def civdef_alert_list(active_only: bool = True,
                            severity_min: AlertSeverity = "info") -> list[Alert]
async def civdef_alert_get(alert_id: AlertID) -> AlertEnvelope
async def civdef_alert_subscribe(target_filter: AlertTarget | None = None) -> AsyncIterator[AlertEnvelope]
async def civdef_alert_ack(alert_id: AlertID, status: AckStatus, note: str = "") -> AckReceipt
async def civdef_alert_acks(alert_id: AlertID) -> list[Ack]
async def civdef_role_register(cert: RoleCertificate) -> RegisterReceipt
async def civdef_role_list() -> list[RoleCertificate]
async def civdef_role_revoke(cert_id: str, reason: str) -> RevokeReceipt    # issuer-only
async def civdef_audit_export(alert_id: AlertID | None = None,
                              since: datetime | None = None,
                              format: Literal["jsonl","pdf"] = "jsonl") -> bytes
```

### 4.3 Service class

```python
class CivilDefenseService:
    def __init__(self,
                 bus: CapabilityBus,
                 event_log: EventLog,
                 identity: IdentityService,
                 notifications: NotificationService,
                 federation: FederationService,
                 evidence: EvidenceService | None,
                 region: RegionAdapter,
                 audit_store: AuditChainStore,
                 config: CivDefConfig): ...

    async def publish_alert(self, draft: AlertDraft, publisher_cert: RoleCertificate) -> AlertID: ...
    async def cancel_alert(self, alert_id: AlertID, reason: str, by_cert: RoleCertificate) -> None: ...
    async def receive_alert(self, envelope: AlertEnvelope) -> None: ...
    async def register_role(self, cert: RoleCertificate) -> None: ...
    async def revoke_role(self, cert_id: str, by_cert: RoleCertificate, reason: str) -> None: ...
    async def ack(self, alert_id: AlertID, status: AckStatus, note: str) -> AckReceipt: ...
    async def export_audit(self, ...) -> bytes: ...
```

### 4.4 Region adapter

```python
class RegionAdapter(Protocol):
    region_code: str
    trust_roots: tuple[NodeID, ...]            # public keys of recognised issuers
    role_schema: dict[str, RoleSpec]           # role name → spec
    audit_retention_years: int
    mandatory_severity_minimums: dict[str, AlertSeverity]  # role → max severity it can publish

    def validate_role(self, cert: RoleCertificate) -> None: ...
    def validate_alert(self, draft: AlertDraft, publisher_cert: RoleCertificate) -> None: ...
```

`regions/nrw.py` ships the NRW taxonomy with roles drawn from real-world structure: `DE.NRW.<Kreis>.<Gemeinde>.<Org>.<Role>`, e.g. `DE.NRW.Kleve.Issum.Feuerwehr.Wehrleiter`, `DE.NRW.Kleve.THW.OV.Leiter`, `DE.NRW.Kleve.DRK.Ortsverein.Bereitschaftsleiter`, `DE.NRW.Kleve.KatS.Stabsleiter`. Each role declares maximum severity it may publish, geographic scope it may target, and whether it may co-sign cross-org alerts.

### 4.5 Audit chain store

```python
class AuditChainStore:
    """Append-only, signed, hash-chained audit log.

    Retention is governed by config.audit_retention_years; default is 10 (NRW pragmatic baseline,
    operator must confirm against current Landesarchivgesetz at deployment time).
    """
    async def append(self, entry: AuditEntry) -> None: ...
    async def latest(self) -> AuditEntry | None: ...
    async def get_range(self, start_seq: int, end_seq: int) -> list[AuditEntry]: ...
    async def verify_chain(self, start: int = 0, end: int | None = None) -> VerifyReport: ...
    async def export(self, ...) -> bytes: ...
```

---

## 5. Behaviour

### 5.1 Role certification

Role certificates form a chain to a regional trust root. NRW's trust roots are configured at deployment time and should match published issuer keys (Innenministerium NRW, the Kreis Kleve administration, etc. — note that as of v3.0 these *do not* publish HearthNet-compatible keys; the pilot uses a substitute issuance ceremony where the local Wehrleiter signs certificates after manual identity verification, and a clear migration path to real institutional keys is documented).

A certificate may be:

- **Issued** — signed by an authority that itself chains to a trust root.
- **Active** — within validity window and not revoked.
- **Revoked** — explicitly revoked by issuer; revocation is itself signed and appended to the audit chain.
- **Expired** — past `expires_at`.

Service operations that require a role check the certificate at every invocation. Revocations propagate via federation; a node receiving a revocation must, on next receipt of an alert signed by the revoked cert, refuse delivery and emit `civdef.alert.dropped.revoked`.

### 5.2 Alert publication

```
publish_alert(draft, cert):
  1. cert.holder must equal self.identity                         → else civdef_cert_not_owned
  2. cert active, not revoked, not expired                        → else civdef_cert_invalid
  3. region.validate_role(cert)                                   → else civdef_cert_unrecognised
  4. region.validate_alert(draft, cert) (severity / scope match)  → else civdef_cert_out_of_scope
  5. Construct Alert with publisher_role from cert.role
  6. Sign Alert with self.identity
  7. (optional) collect issuer_attestation if config requires co-sign
  8. Append to audit chain: event="published"
  9. Emit civdef.alert.published event
 10. Distribute:
     - "local"      → notifications via M11 to local subscribers
     - "push"       → mobile-native delivery via M22
     - "federation" → M14 forwarding to federated nodes matching target.region
     - "lora"       → if M29 enabled, set FLAG_PANIC on the next beacon as a presence-of-alert signal
 11. Optionally mirror to evidence graph (M30) as a claim record
 12. Return AlertID
```

If the publisher loses connectivity mid-publish, the audit-chain `published` entry has already been appended locally, so the alert is recoverable on reconnect and re-distributes from there. Idempotent on AlertID.

### 5.3 Targeting

`AlertTarget` is a set of orthogonal filters:

- **region** — hierarchical region code; matches by prefix (`DE.NRW.Kleve` matches `DE.NRW.Kleve.Issum`).
- **bbox** — optional geographic bounding box (overrides region for the precise area).
- **roles** — empty means public; non-empty restricts visibility to certificate holders of those roles.
- **channels** — which delivery mechanisms to use.

A receiving node filters on its own identity's location, registered roles, and active subscriptions. The filter is enforced **client-side at delivery** as well as **publisher-side at distribution**, so a node that mis-claims a role doesn't expose role-only content (the federation forwarder uses publisher-side filtering when forwarding `roles`-restricted alerts).

### 5.4 Acknowledgements

When a role-targeted alert arrives, the recipient may ack with a status:

- `received` — read confirmation.
- `acting` — operationally taking action (e.g., Feuerwehr en route).
- `need_help` — recipient cannot act; help requested.
- `standing_down` — alert handled, recipient disengages.
- `mistaken` — the recipient believes this alert is in error; an attached `note` should explain.

Acks are signed, appended to the audit chain, and visible to the publisher via `civdef.alert.acks(alert_id)`. Public alerts (no `roles` filter) suppress acks unless `config.allow_public_ack=true` — to prevent ack floods on widely-distributed alerts.

### 5.5 Cancellation

Cancellation requires a certificate with cancel scope (typically the original publisher or a same-or-higher role in the same region). A cancellation:

1. Records the cancellation in the audit chain.
2. Emits `civdef.alert.cancelled` to all original delivery channels.
3. Marks the alert inactive in `civdef_alert_list` queries (`active_only=true`).

The original alert is not deleted. Audit retention applies to the cancellation as well.

### 5.6 Audit chain

The audit chain is an append-only, hash-chained, signed log specific to this module. Each entry's `prev_sha` is the SHA-256 of the previous entry's canonicalised body, creating a tamper-evident chain. `verify_chain` walks from genesis (or a checkpoint) verifying signatures and hashes; failure raises `civdef_audit_chain_broken` and is surfaced as a high-priority operator notification.

Audit entries cover: alert published, alert forwarded (with federation hop), alert acked, alert cancelled, role certificate registered, role certificate revoked, audit chain checkpointed. Export produces `jsonl` (machine-readable, default) or `pdf` (operator-readable for legal review, generated via the public `pdf` skill).

Retention is governed by `CIVDEF_AUDIT_RETENTION_YEARS` (default 10 — operator must validate against current NRW Landesarchivgesetz at deployment; the constant is the recommendation, not the law).

### 5.7 Federation interaction

Alerts cross federation boundaries via M14. The federation manifest must declare `civdef` as an advertised capability; otherwise the alert is not forwarded into the neighbouring community. Forwarding nodes append themselves to `AlertEnvelope.federation_hops` for audit, but do not re-sign the alert (the publisher's signature is the source of truth). The receiving community independently audits the alert against its own role schemas; if the publisher's role is not recognised, the alert is delivered with a `civdef.alert.foreign_role` flag and is *not* surfaced as a high-severity push.

### 5.8 LoRa interaction

LoRa beacons (M29) carry no alert content; they carry only presence. When the local node receives a `severity ∈ {emergency, extreme}` alert and LoRa is enabled, the node sets `FLAG_PANIC` on its next beacon and increases beacon cadence to the panic-burst configured in M29. This is a *signal* that something is happening, not a *content* channel. Receivers must consult bus or notifications for the actual alert content.

### 5.9 Failure modes

- **Publisher's cert revoked after publish, before propagation completes**: federation forwarders that have received the revocation drop the in-flight alert; nodes that have not yet seen the revocation propagate normally. Eventually consistent; documented limitation.
- **Audit chain corruption** (disk failure, manual tampering): `verify_chain` detects; the module enters degraded mode where new publishes are blocked until an operator acknowledges and re-checkpoints. Reads continue.
- **Trust root key compromise**: out of scope for v3.0 to *recover* automatically; documented incident response: revoke all certs chaining to the compromised root, rotate root, reissue.
- **Mass-ack flood**: `allow_public_ack=false` default; per-alert ack rate-limit `CIVDEF_ACK_MAX_PER_MINUTE_PER_NODE`.

---

## 6. Errors

| Code                              | When                                                              |
|-----------------------------------|-------------------------------------------------------------------|
| `experimental_disabled`           | Capability called with the flag off                               |
| `civdef_cert_not_owned`           | Publish/ack with a cert whose holder ≠ caller's identity          |
| `civdef_cert_invalid`             | Certificate expired, revoked, or signature broken                 |
| `civdef_cert_unrecognised`        | Issuer chain doesn't terminate at a configured trust root         |
| `civdef_cert_out_of_scope`        | Cert's role/region doesn't authorise the requested action         |
| `civdef_alert_not_found`          | Operation references an unknown AlertID                           |
| `civdef_alert_target_invalid`     | Target region/bbox malformed or outside the issuer's scope        |
| `civdef_audit_chain_broken`       | Hash or signature mismatch in the audit chain                     |
| `civdef_role_revoked`             | Operation attempted with a revoked certificate                    |
| `civdef_region_unsupported`       | No region adapter loaded for the requested region                 |
| `civdef_ack_rate_limited`         | Ack rate exceeded for this alert from this node                   |

---

## 7. Configuration

```python
@dataclass(frozen=True)
class CivDefConfig:
    enabled:                     bool = False
    region:                      str = "DE.NRW"
    audit_retention_years:       int = CIVDEF_AUDIT_RETENTION_YEARS                # 10
    require_issuer_cosign:       dict[AlertSeverity, bool] = field(default_factory=lambda: {
        "info": False, "advisory": False, "warning": False,
        "emergency": True, "extreme": True,
    })
    allow_public_ack:            bool = False
    ack_max_per_minute_per_node: int = CIVDEF_ACK_MAX_PER_MINUTE_PER_NODE           # 5
    federation_forward:          bool = True
    lora_panic_signal:           bool = True
    severity_push_threshold:     AlertSeverity = "warning"   # below this, no mobile push
    trust_roots_extra:           tuple[NodeID, ...] = ()      # operator-added roots
    region_adapter_overrides:    dict[str, str] = field(default_factory=dict)
```

Constants centralised in `hearthnet/constants.py`.

---

## 8. Tests

### 8.1 Unit

- `test_role_cert_chain_to_root` — cert with valid chain → accepted; broken chain → rejected.
- `test_role_cert_expired` — past `expires_at` → `civdef_cert_invalid`.
- `test_alert_signature_roundtrip`.
- `test_target_region_prefix_match` — `DE.NRW.Kleve` matches `DE.NRW.Kleve.Issum`, not `DE.NRW.Wesel`.
- `test_audit_chain_link` — appending entries chains correctly; `verify_chain` returns ok.
- `test_audit_chain_tamper_detected` — flip a byte in the middle; `verify_chain` reports the break.
- `test_severity_cap_per_role` — Wehrleiter publishing `extreme` → `civdef_cert_out_of_scope` if schema caps at `emergency`.
- `test_revocation_propagates` — revoke cert; subsequent alerts from that cert dropped.

### 8.2 Integration

- Two-node alert flow: node A (Wehrleiter cert) publishes `warning` alert targeting `DE.NRW.Kleve.Issum`; node B (resident in Issum, no cert) receives via M11 push.
- Role-targeted alert: A publishes alert with `roles=("DE.NRW.Kleve.THW.OV.Leiter",)`; B (without cert) does not receive; C (with cert) does.
- Federation: A publishes in community X; X federates to Y; Y's resident D receives with `federation_hops=[X]`.
- Cancellation: A cancels; B's alert list moves it to inactive.
- Audit export: publish, ack, cancel; export `jsonl`; round-trip parses and `verify_chain` passes.

### 8.3 Negative / adversarial

- Forged cert chain (random issuer key) → `civdef_cert_unrecognised`.
- Targeting `DE.BY` (outside NRW) from an NRW-only cert → `civdef_alert_target_invalid`.
- Ack flood beyond rate limit → `civdef_ack_rate_limited`.
- Tampered audit chain → publish blocked until operator re-checkpoint.

### 8.4 Tabletop

- Manual scenarios with Issum Feuerwehr volunteers: simulated Hochwasser event, simulated grid outage, simulated industrial incident on the A57. Goals: latency from alert publication to first ack, false-positive ack rate, operator-perceived clarity of UI under stress.

---

## 9. Cross-references

- **Phase 1 M01 Identity** — every cert, alert, ack, and audit entry is signed against M01 identities.
- **Phase 1 M11 Notifications** — alerts surface via notifications with priority mapped from `severity`.
- **Phase 2 M14 Federation** — alerts cross community boundaries via federation.
- **Phase 2 M16 Tokens** — cert validation reuses M16's signature primitives; alert distribution endpoints require `civdef-receive` scoped tokens.
- **Phase 2 M22 Mobile Native** — mobile push for `severity ≥ severity_push_threshold`.
- **Phase 3 M29 LoRa Beacons** — `FLAG_PANIC` corroboration during emergencies.
- **Phase 3 M30 Evidence** — alerts may carry an `evidence_claim` ClaimID; recipients can `evidence.provenance.trace` to see the reasoning chain.
- **Phase 3 X09 Conformance Suite** — civdef has a dedicated conformance section because of audit-chain integrity requirements.

---

## 10. Open research questions

1. **Real institutional keys.** v3.0 uses substitute issuance because NRW authorities do not (yet) publish HearthNet-compatible keys. The migration path — getting the Innenministerium or Kreis Kleve to publish keys and sign initial role certs — is a political process, not a technical one. Documented; out of code scope.

2. **NINA / KATWARN bridge.** A read-only mirror that pulls public NINA alerts and republishes them locally with a `correlation_id` is plausible and would be valuable. Whether it's M31's job or a separate bridge module is undecided.

3. **Multi-Land schema.** The NRW role taxonomy is concrete; Bayern, Niedersachsen, Hessen each have variations (especially around KatS structures). A community-contributed `regions/` directory is the plan; v3.0 ships only NRW.

4. **Co-signing UX.** When `require_issuer_cosign=true` for emergencies, the publisher must obtain a co-signature from a higher-tier issuer. Latency-sensitive. A pre-delegated "emergency co-sign authority" mechanism (similar to OCSP-stapling for certs) is the obvious extension. Not in v3.0.

5. **Public-ack ergonomics.** Public alerts with `allow_public_ack=true` would let citizens self-report ("I am safe", "I need help"), but the failure modes (ack flood, false reports) are severe enough that v3.0 defaults this off. A future tier with rate limits and ack-content moderation is plausible.

6. **Legal retention.** `CIVDEF_AUDIT_RETENTION_YEARS=10` is the operator-friendly default. Actual legal retention varies (NRW Landesarchivgesetz, federal data retention rules for civil-defence records, GDPR exceptions for vital interests). The deployment guide must explicitly walk operators through this; we cannot guess from code.

7. **Cross-border alerts.** Issum borders the Netherlands. An alert about a Dutch industrial incident might originate from a Dutch system. Cross-border interop is interesting and outside v3.0 scope. The `region` adapter pattern doesn't preclude it.

8. **Drills and false-alarm semantics.** A drill should look real enough to be useful and clearly different enough to not panic non-participants. A `drill=true` flag on Alert is the obvious addition; v3.0 omits it pending feedback from real drill rehearsals.

---

*Last updated: spec v3.0.*
