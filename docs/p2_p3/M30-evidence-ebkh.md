# M30 — Evidence Graph & EBKH Integration

**Spec version:** v3.0 — *experimental*
**Depends on:** [M03 Capability Bus](../../modules/M03-capability-bus.md), [X02 Event Log](../../cross-cutting/X02-events.md), [M01 Identity](../../modules/M01-identity.md), [M06 Files](../../modules/M06-files.md), [M07 Knowledge Base](../../modules/M07-knowledge-base.md), [M16 Tokens](../../phase-2/modules/M16-tokens.md), [M21 Tool Calls](../../phase-2/modules/M21-tool-calls.md)
**Depended on by:** M31 Civil Defense (alerts may carry an evidence chain); RAG quality reports

---

## 1. Responsibility

A **content-addressed claim graph** layered alongside the append-only event log, plus an integration adapter for Christof's existing **EBKH v3+** (event-sourced knowledge hub with OSINT capabilities, PostGIS, and the class-reference graph already described in his upstream work).

The event log answers "what happened, in what order". The evidence graph answers a different question: "what is asserted, by whom, on what basis, and what counterclaims exist?" This is necessary because in a community AI mesh, *information has provenance* — a claim about when the Sankt Martins parade starts, where the local emergency assembly point is, or what the Volksbank's IBAN is — must be traceable to a source, must be cross-checkable, and must support dispute. The event log doesn't do that; it just records that someone said something.

The module is small in line count but conceptually load-bearing: it defines what counts as evidence, what a claim is, how claims compose, and how the rest of the stack queries provenance. The EBKH adapter wires this to Christof's already-built PostGIS + OSINT infrastructure so the two systems converge rather than duplicate.

---

## 2. Non-goals

- **Replacing the event log.** The event log is still the source of truth for *what happened*. The evidence graph is a *derived* view over claims extracted from events plus claims asserted directly.
- **Adjudicating truth.** The module records claims, disputes, and attestations. It does not decide who is right.
- **General-purpose knowledge graph.** This is not a Wikidata clone. The schema is deliberately narrow: claim, source, attestation, dispute, derivation.
- **Replacing RAG.** RAG retrieves passages. The evidence graph annotates those passages with provenance and lets a downstream summariser say "according to source X (last verified Y)". Different layer.
- **OSINT collection.** EBKH already collects from external sources; this module *integrates* with that collector, it does not duplicate it.
- **Mandatory adoption.** RAG and chat can still operate without consulting the evidence graph. The graph is queried when callers explicitly want provenance.

---

## 3. File layout

```
hearthnet/evidence/
├── __init__.py
├── service.py            # EvidenceService — capability handler
├── claim.py              # Claim, ClaimSource, Attestation, Dispute, Derivation dataclasses
├── store.py              # ClaimStore — append-only with content-addressed ClaimIDs
├── query.py              # Provenance traversal: trace(), neighbours(), conflicts()
├── extractor.py          # Pulls claims out of events (chat, KB ingest, federation)
├── ebkh_adapter.py       # Bridge to Christof's EBKH v3+ via JSON-RPC
└── trust.py              # Per-source trust scoring (advisory, no enforcement)
```

---

## 4. Public API

### 4.1 Dataclasses

```python
ClaimID = NewType("ClaimID", str)             # SHA-256 over canonical claim record
SourceID = NewType("SourceID", str)           # "url:https://...", "node:<NodeID>", "doc:<FileID>", "ebkh:<entity_uri>"

EvidenceLevel = Literal[
    "unverified",       # claim made, no corroboration
    "cited",            # claim has at least one source
    "cross_referenced", # ≥2 independent sources agree
    "attested",         # an identified party with skin in the game has signed
    "disputed",         # at least one counterclaim with sources
]

@dataclass(frozen=True)
class ClaimSource:
    source_id:    SourceID
    accessed_at:  datetime
    content_sha:  str | None              # SHA of the cited content if available
    excerpt:      str | None              # short verbatim excerpt; max 280 chars

@dataclass(frozen=True)
class Claim:
    claim_id:        ClaimID
    subject:         str                   # canonical subject string
    predicate:       str                   # e.g. "starts_at", "located_at", "operated_by"
    object:          str                   # canonical object string
    asserted_by:     NodeID
    asserted_at:     datetime
    sources:         tuple[ClaimSource, ...]
    confidence:      float                 # asserter's self-rated confidence [0,1]
    derived_from:    tuple[ClaimID, ...]   # parent claims if this is a derivation
    signature:       bytes                 # asserter's Ed25519 signature

@dataclass(frozen=True)
class Attestation:
    claim_id:     ClaimID
    attester:     NodeID
    attested_at:  datetime
    rationale:    str                      # human-readable "I know this because..."
    role:         str                      # "first-hand witness", "official record holder", "expert"
    signature:    bytes

@dataclass(frozen=True)
class Dispute:
    claim_id:        ClaimID               # the claim being disputed
    counterclaim_id: ClaimID               # the claim made in response
    disputer:        NodeID
    disputed_at:     datetime
    rationale:       str
    signature:       bytes

@dataclass(frozen=True)
class ProvenanceTrace:
    claim:           Claim
    sources:         tuple[ClaimSource, ...]
    attestations:    tuple[Attestation, ...]
    disputes:        tuple[Dispute, ...]
    derivation_tree: tuple[Claim, ...]     # walked depth-first, deduplicated
    evidence_level:  EvidenceLevel
    trust_score:     float                 # advisory; from trust.py
```

### 4.2 Capabilities

All under `experimental.evidence.*`:

```python
async def evidence_claim_assert(draft: ClaimDraft) -> ClaimID
async def evidence_claim_dispute(claim_id: ClaimID, counterclaim: ClaimDraft, rationale: str) -> ClaimID
async def evidence_claim_attest(claim_id: ClaimID, role: str, rationale: str) -> AttestationReceipt
async def evidence_claim_get(claim_id: ClaimID) -> Claim
async def evidence_claim_query(subject: str | None = None,
                                predicate: str | None = None,
                                object: str | None = None,
                                min_evidence: EvidenceLevel = "unverified") -> list[Claim]
async def evidence_provenance_trace(claim_id: ClaimID, max_depth: int = 5) -> ProvenanceTrace
async def evidence_subject_summary(subject: str) -> SubjectSummary
async def evidence_ebkh_sync(direction: Literal["pull","push","bidi"] = "bidi") -> SyncReport
```

### 4.3 Service class

```python
class EvidenceService:
    def __init__(self,
                 bus: CapabilityBus,
                 event_log: EventLog,
                 identity: IdentityService,
                 store: ClaimStore,
                 extractor: ClaimExtractor,
                 ebkh: EbkhAdapter | None,
                 trust: TrustScorer,
                 config: EvidenceConfig): ...

    async def assert_claim(self, draft: ClaimDraft) -> ClaimID: ...
    async def dispute(self, claim_id: ClaimID, counterclaim: ClaimDraft, rationale: str) -> ClaimID: ...
    async def attest(self, claim_id: ClaimID, role: str, rationale: str) -> AttestationReceipt: ...
    async def trace(self, claim_id: ClaimID, max_depth: int) -> ProvenanceTrace: ...
    async def summarise_subject(self, subject: str) -> SubjectSummary: ...
    async def evidence_level(self, claim_id: ClaimID) -> EvidenceLevel: ...
```

### 4.4 Claim store

```python
class ClaimStore:
    async def put(self, claim: Claim) -> ClaimID: ...        # idempotent on ClaimID
    async def get(self, claim_id: ClaimID) -> Claim | None: ...
    async def by_subject(self, subject: str) -> list[Claim]: ...
    async def by_triple(self, subject: str, predicate: str, object: str | None) -> list[Claim]: ...
    async def disputes_of(self, claim_id: ClaimID) -> list[Dispute]: ...
    async def attestations_of(self, claim_id: ClaimID) -> list[Attestation]: ...
    async def derivatives_of(self, claim_id: ClaimID) -> list[Claim]: ...
```

The store is append-only. A "retraction" is itself a claim (`predicate="retracted"`, `object="<claim_id>"`) and is treated as a special kind of dispute by the trace algorithm.

### 4.5 Extractor

```python
class ClaimExtractor:
    """Watches the event log and proposes claims from candidate events.

    Proposals are *suggestions*, not auto-asserted. A claim only enters
    the store when an identified asserter signs it.
    """
    async def consume(self, evt: Event) -> list[ClaimDraft]: ...
    def register_pattern(self, predicate: str, matcher: Callable[[Event], ClaimDraft | None]) -> None: ...
```

Patterns shipped in v3.0:

- KB ingest event → `claim(doc_sha, "contains_text", text_hash)` with the doc as source.
- Tool-call event (M21) with HTTP fetch → `claim(url, "served", content_sha)` with the URL as source.
- Federation manifest event → `claim(remote_node, "advertises_capability", cap_name)` with the manifest as source.
- LoRa beacon (M29) reception → *not* auto-extracted; presence is logged but not claimed.

### 4.6 EBKH adapter

```python
class EbkhAdapter:
    def __init__(self, endpoint: str, token: str, postgis_dsn: str | None = None): ...

    async def push_claim(self, claim: Claim) -> EbkhRef: ...
    async def pull_entity(self, entity_uri: str) -> list[Claim]: ...
    async def query_spatial(self, bbox: Bbox, predicate: str | None = None) -> list[Claim]: ...
    async def sync(self, direction: Literal["pull","push","bidi"]) -> SyncReport: ...
```

The adapter speaks EBKH's JSON-RPC over HTTPS with an Ed25519-bound bearer token (issued via M16). Spatial queries piggy-back on EBKH's PostGIS layer — useful for civil-defence claims like "Sammelplatz is at geom(...)". For nodes without EBKH installed, the adapter is `None` and capabilities still function on the local claim store only.

### 4.7 Trust scoring

`TrustScorer` produces an advisory `[0,1]` score for a source. The function is intentionally simple and visible:

```python
class TrustScorer:
    def score_source(self, source: ClaimSource, context: TrustContext) -> float: ...
    def score_asserter(self, node_id: NodeID, context: TrustContext) -> float: ...
```

Inputs include: how long the source has been known, how many of its prior claims were not disputed, whether it's signed by a verified identity, whether it's in an operator-curated allowlist or blocklist. The score is **always shown alongside the claim, never hidden**, and never causes a claim to be omitted from query results — only re-ranked. Operators can override individual scores.

---

## 5. Behaviour

### 5.1 Canonicalisation and ClaimID

A claim's identity is its `ClaimID`, defined as:

```
ClaimID = base32-no-pad( SHA-256( JCS({
    subject, predicate, object,
    asserted_by, asserted_at_iso8601,
    sources: [{source_id, accessed_at_iso, content_sha} ...],
    confidence_5dp,
    derived_from: [...sorted ClaimIDs...],
}) ) )
```

The signature is *not* part of the ClaimID — a different asserter making the identical claim would produce a different signature but the same record. To distinguish, we use `Claim.asserted_by` and the signature ensures non-repudiation. A claim asserted twice by the same node at the same instant with the same sources is genuinely the same claim and the store deduplicates.

### 5.2 Evidence level computation

```
unverified       = no sources
cited            = ≥1 source
cross_referenced = ≥2 sources, distinct source_ids, ≥1 not from asserter's own node
attested         = ≥1 attestation with role in {"first-hand witness","official record holder"}
disputed         = ≥1 unretracted dispute by a node with trust_score ≥ EVIDENCE_DISPUTE_MIN_TRUST
```

Levels are not mutually exclusive in nature, but the API returns the *strongest applicable level* with `disputed` taking precedence over everything else if present. This way callers default to "show that there's a dispute" rather than burying it under a stronger-sounding label.

### 5.3 Provenance trace algorithm

`trace(claim_id, max_depth)` does a depth-first walk over `derived_from` edges, deduplicates by ClaimID, and collects every source, attestation, and dispute encountered. The walk stops at `max_depth` (default 5) or at a cycle (cycles shouldn't exist by construction, but we guard anyway).

The result is a flat tuple in topological order from root claim outward. UI is expected to render this as a tree or a list, with disputes inlined wherever they occur.

### 5.4 Subject summary

`summarise_subject(subject)` is the workhorse for the rest of the stack. It returns:

- All claims with this subject, grouped by predicate.
- For each predicate, the strongest claim by evidence level and trust score.
- All disputes affecting this subject.
- A flat list of distinct sources contributing.

This is what a RAG pipeline calls to add provenance to its retrieved passages, and what civil-defence (M31) calls to verify a target before publishing an alert.

### 5.5 EBKH sync

`evidence.ebkh.sync` runs in three modes:

- **pull** — fetch claims for subjects in our local store from EBKH, add as new claims (asserted by the EBKH node identity).
- **push** — send our locally-asserted claims to EBKH; EBKH stores them tagged with our node ID.
- **bidi** — both, in that order.

Sync is idempotent. Each side stores the other-side's claim records; nothing is overwritten. Conflicts (same triple, different sources) become co-existing claims, and disputes can be raised normally.

EBKH's existing PostGIS schema is reused for spatial predicates. The adapter does *not* try to model the full EBKH schema in our claim graph; it surfaces what is asked for and lets EBKH remain the authoritative store for OSINT-collected material.

### 5.6 Failure modes

- **Claim signature invalid** on receipt from another node → reject; emit `security.signature.invalid`.
- **Dispute on a non-existent claim** → `claim_not_found`.
- **Cyclic derivation** → reject the new claim; `evidence_cycle_detected`. (This can only happen via malicious crafting; honest derivation cannot cycle.)
- **EBKH unreachable** during sync → return a `SyncReport` with `partial=true` and the unreachable error; do not fail the calling operation.

---

## 6. Errors

| Code                              | When                                                              |
|-----------------------------------|-------------------------------------------------------------------|
| `experimental_disabled`           | Capability called with the flag off                               |
| `claim_not_found`                 | Operation references a ClaimID we don't have                      |
| `claim_signature_invalid`         | Signature doesn't verify against asserter's identity              |
| `evidence_cycle_detected`         | Proposed claim's derivation chain forms a cycle                   |
| `evidence_contradiction`          | (advisory) two claims with the same triple but opposite objects   |
| `ebkh_unavailable`                | EBKH endpoint not configured or unreachable                       |
| `trust_below_threshold`           | (advisory) attached to results; not an error condition by itself  |

`evidence_contradiction` is *advisory* — returned in query results as a flag, not raised as an exception. The system never silently picks a winner.

---

## 7. Configuration

```python
@dataclass(frozen=True)
class EvidenceConfig:
    enabled:                  bool = False
    auto_extract:             bool = True              # let extractor propose drafts
    extract_patterns:         tuple[str, ...] = ("kb_ingest","tool_fetch","federation_manifest")
    claim_ttl_days:           int  = EVIDENCE_CLAIM_TTL_DAYS_DEFAULT          # 365
    trust_default:            float = 0.5
    dispute_min_trust:        float = EVIDENCE_DISPUTE_MIN_TRUST               # 0.3
    ebkh_endpoint:            str | None = None
    ebkh_token_scope:         str = "evidence-sync"
    ebkh_sync_interval_minutes: int = 60
    max_provenance_depth:     int = EVIDENCE_MAX_PROVENANCE_DEPTH              # 8
    summary_max_predicates:   int = 32
```

Constants live in `hearthnet/constants.py`. `claim_ttl_days` does not delete claims — it marks them as stale for query purposes; the actual record is permanent.

---

## 8. Tests

### 8.1 Unit

- `test_claim_id_canonicalisation` — re-ordering source list or whitespace changes do not affect ClaimID.
- `test_claim_signature_roundtrip`.
- `test_evidence_level_disputed_wins` — a claim with two sources *and* a dispute returns `disputed`.
- `test_provenance_trace_dedup` — diamond derivation graph yields each ancestor once.
- `test_extractor_kb_ingest_pattern` — KB ingest event produces a draft with the right predicate.
- `test_retraction_is_dispute` — a retraction shows up in `disputes_of`.

### 8.2 Property

- For random claims, `evidence_level(c)` is monotonic when adding sources/attestations and falls to `disputed` on adding a dispute.
- For random derivation DAGs, `trace(root)` yields exactly the reachable set.

### 8.3 Integration

- KB ingest → claim drafted → operator asserts → query returns it.
- Dispute lifecycle: assert claim, attest it, dispute it, see `evidence_level=disputed`, retract the dispute (as a dispute-of-the-dispute), verify level returns to `attested`.
- EBKH adapter against a mock JSON-RPC endpoint: round-trip a spatial claim, verify the bbox query returns it.
- Federated extraction: a federation manifest event from M14 produces a claim about advertised capabilities, which is then visible to subject-query `summarise_subject(<remote_node_id>)`.

### 8.4 Negative

- Cyclic derived_from input → `evidence_cycle_detected`.
- Claim signed by an unknown identity → `claim_signature_invalid`.
- EBKH endpoint configured but unreachable → `sync` returns partial; capability does not raise.

---

## 9. Cross-references

- **Phase 1 M01 Identity** — every claim is signed; signatures verified against M01.
- **Phase 1 M06 Files** — `doc:<FileID>` sources resolve to content-addressed files.
- **Phase 1 M07 Knowledge Base** — KB ingest events feed the extractor.
- **Phase 1 X02 Event Log** — `evidence.claim.*`, `evidence.dispute.*`, `evidence.attestation.*` events.
- **Phase 2 M21 Tool Calls** — fetched URLs are extracted as claims for downstream provenance.
- **Phase 3 M31 Civil Defense** — alerts carry a top-level claim ID, allowing recipients to trace why an alert was issued.
- **Phase 3 X09 Conformance Suite** — provenance-trace correctness is part of the experimental suite.
- **External: EBKH v3+** — Christof's existing event-sourced knowledge hub; PostGIS-backed; this module is the integration point.

---

## 10. Open research questions

1. **Claim semantics.** "subject/predicate/object" is intentionally loose. Whether to adopt RDF, JSON-LD, or a custom ontology with a controlled vocabulary is unsettled. v3.0 accepts free strings and ships a small recommended vocabulary in the docs.

2. **Trust composition.** When a derived claim depends on three parent claims of varying trust, what's the derived trust? Min, product, weighted-average? Currently the trust scorer ignores derivation. A future version may compose explicitly.

3. **Dispute escalation.** Today a dispute is a single counter-claim. In practice, communities will want threaded discussion attached to disputes. Whether this belongs here or in M10/M25 chat is a design call.

4. **Time-bound claims.** "The Volksbank opens at 9:00" is true on weekdays but not Sundays. The schema has no first-class temporal modality. A pragmatic workaround is encoding temporal qualifiers into the predicate ("opens_at_weekday"), but a proper temporal logic layer would be cleaner. Out of scope.

5. **Confidentiality.** Some claims are sensitive (a neighbour's medical condition, a Feuerwehr member's home address). The current model has no claim-level access control. The capability-bus tokens (M16) can scope access to the evidence service entirely, but not at a per-claim granularity. Open.

6. **OSINT integration boundaries.** EBKH ingests from external feeds. When does an external feed become a sufficiently authoritative source to upgrade evidence level? The pragmatic stance in v3.0 is "operator decides via the trust allowlist". A future version may automate this.

7. **Visualisation.** Provenance trees get big fast. A graph visualisation widget (probably d3 in plain HTML) would help operators. Specced but unbuilt.

8. **Federated claim propagation.** Two communities federate, and one asserts a claim relevant to the other. Should it auto-mirror? Today, no — claims propagate only when explicitly queried via `ebkh_sync` or fetched on demand. A push model would be possible but worsens consent.

---

*Last updated: spec v3.0.*
