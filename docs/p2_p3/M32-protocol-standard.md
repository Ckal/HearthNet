# M32 — Protocol Standardisation & Conformance

**Spec version:** v3.0 — *experimental*
**Depends on:** [M03 Capability Bus](../../modules/M03-capability-bus.md), [X02 Event Log](../../cross-cutting/X02-events.md), [M14 Federation](../../phase-2/modules/M14-federation.md), [X09 Conformance Suite](../cross-cutting/X09-conformance-suite.md)
**Depended on by:** anyone building an alternate implementation of HearthNet

---

## 1. Responsibility

Turn the HearthNet specs from "Christof's working code with documentation" into something a **second team** could implement compatibly. This module is the bookkeeping for that: a versioned protocol document set, a conformance reporting capability, governance for how the spec changes, and a registry of known implementations and their conformance levels.

The premise is that long-term, a single implementation is fragile. If HearthNet only works as long as one person maintains it, it doesn't survive. Standardising the protocol (the wire formats, the capability contracts, the federation semantics) so other implementations can interoperate is the path to durability — and it sets up the social and legal scaffolding (versioning policy, change process, conformance claims) that other projects will need to take HearthNet seriously.

This is not "rewrite HearthNet as an RFC". It's "package what already exists in a form that can be cited, versioned, and conformance-tested". The reference implementation is HearthNet itself; the protocol document is the contract; the conformance suite (X09) is the proof.

---

## 2. Non-goals

- **Submitting to IETF / W3C in v3.0.** That's a multi-year governance process and is out of scope. We make ourselves *ready* for it by structuring the documents and adopting RFC-style versioning conventions, but we don't file anything.
- **Patent licensing.** There are no patented techniques in HearthNet's core (capability bus, event log, federation, etc. — all build on well-known primitives). We document this assumption but do not run a patent review.
- **Trademark of "HearthNet".** Out of scope. If the protocol survives, someone (probably ki-fusion-labs.de) eventually claims the name; v3.0 doesn't deal with that.
- **Conformance certification with a fee structure.** Conformance reports are self-published and free. No "HearthNet Inside™ certification programme".
- **Backward compatibility forever.** Protocol versions can have breaking changes between major versions, with documented migration. Within a minor version, compatibility is required.

---

## 3. File layout

The module is unusual in that most of its content lives *outside* the `hearthnet/` Python package — in a top-level `protocol/` directory at the repository root.

```
protocol/                                # repo-root sibling of hearthnet/
├── README.md
├── VERSION                              # current protocol version (e.g. 3.0.0)
├── CHANGELOG.md
├── governance.md                        # change process, decision rights
├── versioning.md                        # semver-with-twists rules
├── reference-implementations.md         # registry
├── core/
│   ├── 01-identity-and-addressing.md
│   ├── 02-transport.md
│   ├── 03-capability-bus.md
│   ├── 04-event-log.md
│   ├── 05-tokens.md
│   ├── 06-federation.md
│   └── ...
└── experimental/
    ├── 30-evidence.md
    └── 31-civil-defense.md

hearthnet/protocol/
├── __init__.py
├── service.py                           # ProtocolService — registry and report capability
├── registry.py                          # In-memory + persisted registry of known impls
└── report.py                            # Conformance report dataclass + serialiser
```

The `protocol/` directory is the **specification artefact** — versioned alongside code but conceptually independent. The Python `hearthnet/protocol/` module is the thin runtime surface that lets a HearthNet node expose its conformance information on the bus.

---

## 4. Public API

### 4.1 Dataclasses

```python
@dataclass(frozen=True)
class ProtocolVersion:
    major:  int
    minor:  int
    patch:  int
    suffix: str = ""        # "", "rc1", "experimental"

    def __str__(self) -> str: ...        # "3.0.0" or "3.0.0-rc1"
    def is_compatible_with(self, other: ProtocolVersion) -> bool: ...   # same major

@dataclass(frozen=True)
class ImplementationDescriptor:
    name:           str                  # e.g. "hearthnet-reference"
    vendor:         str                  # e.g. "ki-fusion-labs.de"
    version:        str                  # implementation version, e.g. "0.4.2"
    protocol_versions: tuple[ProtocolVersion, ...]   # which protocol versions supported
    homepage_url:   str | None
    contact:        str | None

@dataclass(frozen=True)
class ConformanceReport:
    implementation:  ImplementationDescriptor
    protocol_version: ProtocolVersion
    suite_version:   str                   # X09 conformance suite version
    ran_at:          datetime
    sections: dict[str, SectionResult]     # section name → result
    overall: Literal["pass","fail","partial","skipped"]
    signature: bytes                       # implementation signs its own report

@dataclass(frozen=True)
class SectionResult:
    name:          str
    total:         int
    passed:        int
    failed:        int
    skipped:       int
    failures:      tuple[FailureDetail, ...]
```

### 4.2 Capabilities

```python
async def protocol_version_list() -> list[ProtocolVersion]
async def protocol_self_describe() -> ImplementationDescriptor
async def protocol_conformance_report(suite_version: str | None = None) -> ConformanceReport
async def protocol_registry_list() -> list[ImplementationDescriptor]
async def protocol_registry_announce(descriptor: ImplementationDescriptor) -> AnnounceReceipt
```

These are stable (non-experimental) capabilities — the protocol must include its own self-description and conformance-reporting capability, otherwise interop is impossible.

### 4.3 Service class

```python
class ProtocolService:
    def __init__(self,
                 bus: CapabilityBus,
                 event_log: EventLog,
                 federation: FederationService,
                 registry: ImplementationRegistry,
                 conformance_runner: ConformanceRunner | None,
                 config: ProtocolConfig): ...

    def supported_versions(self) -> list[ProtocolVersion]: ...
    def self_descriptor(self) -> ImplementationDescriptor: ...
    async def run_conformance(self, suite_version: str | None = None) -> ConformanceReport: ...
    async def announce(self, descriptor: ImplementationDescriptor) -> None: ...   # to local registry + federation
    async def registry_list(self) -> list[ImplementationDescriptor]: ...
```

### 4.4 Implementation registry

```python
class ImplementationRegistry:
    """Local registry of known implementations.

    Populated by:
      - self (this node, on startup)
      - federation peers' announcements
      - operator-curated additions
    """
    async def upsert(self, descriptor: ImplementationDescriptor, source: NodeID) -> None: ...
    async def list(self) -> list[ImplementationDescriptor]: ...
    async def known_by_name(self, name: str) -> list[ImplementationDescriptor]: ...
```

---

## 5. Behaviour

### 5.1 Versioning policy

Protocol versions follow **semver with explicit stability tiers**:

- **Major** (`X.0.0`): breaking changes to wire formats or capability contracts. New major version requires explicit migration documentation. Old majors remain readable for migration purposes for at least 2 years.
- **Minor** (`X.Y.0`): additive — new capabilities, new event types, new optional fields. Backward compatibility within the major is required: a `3.0` impl talking to a `3.2` impl must work, with the `3.0` side ignoring new fields/events.
- **Patch** (`X.Y.Z`): clarification, typo fixes, no functional change.
- **Suffix** `-experimental`: capabilities in the `experimental.*` namespace; can change without bumping major.

Each protocol document carries a frontmatter `protocol-version: 3.X.Y` that names the smallest version that contains it. The `protocol/VERSION` file is the current latest. The `CHANGELOG.md` lists every diff between versions.

### 5.2 Stability tiers

Capabilities are tagged with one of:

- `stable` — frozen at the major version; any change is a breaking change.
- `provisional` — expected to become stable; minor-version breaking changes allowed with deprecation period.
- `experimental` — `experimental.*` namespace; may change or vanish.

The `protocol_self_describe` capability reports which capabilities the implementation supports and at which tier. A capability marked `stable` in the protocol but implemented at `experimental` tier in the node is a configuration error and is logged at startup.

### 5.3 Conformance reporting

A `ConformanceReport` is the artefact produced by running the X09 conformance suite against a running node. The report is:

- **Self-signed** by the implementation — there is no central authority that "certifies" reports.
- **Reproducible** — the suite version is in the report; running the same suite against the same impl should produce equivalent results modulo timestamps.
- **Public** — implementations are encouraged to publish their reports openly (in their repo, on their website, federated via the registry).
- **Honest about partial conformance** — `partial` is a valid outcome and is more useful than a misleading `pass`.

Reports do not expire, but a report from suite version `1.0.0` is not equivalent to a report from `2.0.0`. The X09 suite versions independently of the protocol.

### 5.4 Implementation registry & federation

Each HearthNet node announces its `ImplementationDescriptor` to its federation peers on connect. Peers add it to their local registry. Operators can query their local registry for "who else is out there" via `protocol_registry_list`.

The registry is *advisory*. There is no trust beyond "this peer claimed this descriptor at this time". A peer claiming to be an implementation it isn't is a security incident, but the registry doesn't authenticate vendor names — only that the node signed its descriptor.

### 5.5 Governance (documented, not enforced)

The `protocol/governance.md` document describes how protocol changes happen:

1. **Proposal**: any contributor writes a "change note" as a PR to `protocol/`. Includes motivation, exact spec diff, migration story, and conformance impact.
2. **Discussion**: open period (default 4 weeks) for review.
3. **Decision**: maintainers (initially just Christof, ideally expanding to a small group) accept, reject, or request revision. Rejections are logged with rationale.
4. **Merge**: accepted change merges to `protocol/main` with version bump per §5.1 rules.
5. **Release**: tagged release of the protocol document set independent of code releases.

This is a process document; the module does not *enforce* governance technically. Enforcement is social.

### 5.6 Reference implementations registry

`protocol/reference-implementations.md` is a living document listing known implementations. v3.0 entries:

- **hearthnet-reference** (Python, this codebase). Status: complete, all stable + provisional + experimental capabilities.
- (placeholder for a second impl when one exists).

Adding an implementation to this document requires a PR demonstrating at minimum a passing conformance report for `core` sections of the X09 suite at the current major version.

### 5.7 Migration documentation

Each major version transition ships a `protocol/migration/X-to-Y.md` document. v3.0 includes:

- `protocol/migration/2-to-3.md` — placeholder for now; v3.0 introduces only experimental capabilities, so a strict v2→v3 migration is effectively a no-op for stable code paths.

### 5.8 Failure modes

- **Mismatched protocol versions in federation**: handled by M14 federation manifest version negotiation. M32 itself doesn't intervene at runtime; it just reports.
- **Conformance suite not present**: `protocol.conformance.report` returns `skipped` overall with reason `suite_not_installed`.
- **Conflicting registry entries** (same `name` claimed by two distinct vendors): both stored; the registry list returns both; operators decide.

---

## 6. Errors

| Code                          | When                                                              |
|-------------------------------|-------------------------------------------------------------------|
| `protocol_version_unknown`    | Operation references a protocol version not in our table         |
| `protocol_suite_not_installed`| Conformance report requested but X09 not available               |
| `protocol_descriptor_invalid` | Announcement with malformed descriptor                            |
| `protocol_unsupported_capability` | Federation negotiation finds no compatible major version       |

---

## 7. Configuration

```python
@dataclass(frozen=True)
class ProtocolConfig:
    enabled:                  bool = True       # this one is enabled by default
    supported_versions:       tuple[str, ...] = ("3.0.0",)
    default_announce_version: str = "3.0.0"
    descriptor:               ImplementationDescriptor = field(default_factory=lambda: ImplementationDescriptor(
        name="hearthnet-reference",
        vendor="ki-fusion-labs.de",
        version="0.4.2",
        protocol_versions=(ProtocolVersion(3, 0, 0),),
        homepage_url="https://ki-fusion-labs.de/hearthnet",
        contact=None,
    ))
    announce_to_federation:   bool = True
    conformance_auto_run_on_startup: bool = False
    registry_max_entries:     int = 4096
```

---

## 8. Tests

### 8.1 Unit

- `test_protocol_version_compat` — same major compatible; different major not.
- `test_descriptor_signature_roundtrip`.
- `test_registry_upsert_idempotent`.
- `test_conformance_report_signed` — self-signed report's signature verifies against the implementation's identity.
- `test_protocol_version_parse` — `"3.0.0"`, `"3.0.0-rc1"`, `"3.0.0-experimental"` parse correctly.

### 8.2 Integration

- Two nodes (same impl, same version): announce → registry shows both.
- Two nodes (same impl, different versions): registry shows both; federation negotiates highest compatible.
- Run conformance suite against the reference impl: must pass `core/*` sections by definition (the suite is built to match the spec).

### 8.3 Spec-document tests

- `test_protocol_documents_present` — every protocol document referenced in `protocol/README.md` exists.
- `test_protocol_version_consistent` — `protocol/VERSION` matches the `default_announce_version` in code.
- `test_changelog_format` — `protocol/CHANGELOG.md` parses as a sequence of versioned entries with semver-valid ordering.

### 8.4 Negative

- Malformed descriptor → `protocol_descriptor_invalid`.
- Federation peer announces protocol `99.0.0` → registry stores it, federation negotiation declines.

---

## 9. Cross-references

- **All Phase 1, 2, 3 modules** — they collectively *are* the protocol. M32's job is the meta-layer.
- **Phase 2 M14 Federation** — federation manifest carries protocol version; negotiation uses M32's compat rules.
- **Phase 3 X09 Conformance Suite** — produces the data that M32's report capability surfaces.

---

## 10. Open research questions

1. **Independent implementation.** The protocol is real only when a second implementation exists. v3.0 ships only the reference. A small "minimal HearthNet" written in Go or Rust as a contrast implementation would prove the spec is implementable from the documents alone. Concrete next step, but not in v3.0.

2. **Formal verification of wire formats.** TLS-style formal proofs of the federation handshake and capability-bus dispatch would be valuable. Out of v3.0 scope; documented as a research direction.

3. **Governance bootstrapping.** "Christof decides" is fine for now and honest about the project's state. Transitioning to a multi-maintainer model needs a path — a Tech Steering Committee, a foundation, or simply a documented succession plan. Currently undefined.

4. **Standards-body engagement.** If the protocol matures, IETF (for federation/transport) and W3C (for capability-bus semantics if they look RPC-like) are plausible homes. v3.0 deliberately avoids premature standards engagement; the bar is "second implementation exists and is interoperable".

5. **Legal entity.** ki-fusion-labs.de is currently the operating entity. Whether a separate legal entity (e.V., foundation) is needed for a multi-vendor protocol is a real question. Out of code scope.

6. **Trademark and naming.** "HearthNet" as a trademark is undefined; the protocol could be renamed to something more obviously generic at standardisation time. The reference impl can keep the name.

7. **Optionality flags vs separate profiles.** A node might support `core` only, or `core + federation`, or everything. Whether to model this as per-capability optionality (current approach) or named profiles (`HearthNet-Core`, `HearthNet-Federated`, `HearthNet-Civdef`) is a design question that needs feedback from a second impl team.

8. **Conformance suite drift.** The X09 suite is the source of truth for "what does conformance mean"; the protocol documents describe the *intent*. When the two disagree, currently the suite wins (because it's executable). This is pragmatic but not principled. A future version may flip this and use the suite to *test* the documents, with the documents as primary.

---

*Last updated: spec v3.0.*
