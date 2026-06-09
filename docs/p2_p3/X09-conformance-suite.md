# X09 — Conformance Suite

**Spec version:** v3.0 — *experimental*
**Depends on:** Every other module (the suite tests them); no runtime dependency in production
**Depended on by:** [M32 Protocol Standardisation](../modules/M32-protocol-standard.md)

---

## 1. Purpose

A black-box, implementation-agnostic test suite that defines what "HearthNet-compliant" means in practice. The suite spins up an instance of an implementation, drives it through specified interactions, observes the wire format and the capability behaviour, and produces a `ConformanceReport` (defined in M32).

Where the spec documents say "the system MUST do X", the conformance suite contains a test that observes whether the system does X. If a behaviour is described in a spec but not tested by X09, the spec wins in principle but the suite wins in practice — so we treat closing that gap as a continuous effort.

The suite is designed so that an alternate implementation (a future Go or Rust HearthNet) can be tested by the same suite. This is the entire point: it makes "interoperable" a measurable property.

---

## 2. Non-goals

- **Replacing per-module unit tests.** Each module ships its own unit and property tests as described in its spec. X09 sits one level higher and treats the implementation as a black box.
- **Performance benchmarks.** Conformance is correctness, not speed. A future X10 may handle benchmarks.
- **Security audits.** Out of scope. The suite includes some negative-path tests but is not a pen-test.
- **Visual / UX testing.** The web UI is exercised only via its capability-bus and HTTP API surfaces.
- **Locking in implementation detail.** Tests assert on observable behaviour (wire formats, capability responses, event log entries), never on internal state.

---

## 3. File layout

The suite lives at repository root, sibling to `hearthnet/` and `protocol/`:

```
conformance/
├── README.md
├── VERSION                            # suite version, e.g. "1.0.0"
├── pyproject.toml                     # standalone tool, runnable without hearthnet/
├── runner.py                          # entry point: `python -m conformance.runner --target=...`
├── report.py                          # builds ConformanceReport from results
├── harness/
│   ├── target.py                      # abstraction over a "system under test" (SUT)
│   ├── docker_target.py               # SUT in a docker container
│   ├── local_target.py                # SUT on the local network at a URL
│   ├── fixtures.py                    # synthetic identities, tokens, files
│   └── wire_capture.py                # records bus / WS traffic for diffing
├── suites/
│   ├── core/
│   │   ├── identity/
│   │   ├── transport/
│   │   ├── bus/
│   │   ├── events/
│   │   ├── tokens/
│   │   ├── files/
│   │   ├── kb/
│   │   └── llm/
│   ├── services/
│   │   ├── chat/
│   │   ├── group_chat/
│   │   ├── ocr/
│   │   ├── translation/
│   │   └── stt_tts/
│   ├── federation/
│   ├── experimental/
│   │   ├── distributed_inference/
│   │   ├── moe/
│   │   ├── fedlearn/
│   │   ├── evidence/
│   │   └── civdef/
│   └── operability/
│       ├── shutdown_clean/
│       ├── restart_persistence/
│       └── observability/
└── vectors/                           # test vectors: canonical inputs and expected outputs
    ├── identity/
    ├── tokens/
    ├── federation/
    └── tensor_transport/
```

The whole `conformance/` directory is published as part of every protocol release, with the `VERSION` file aligning with the protocol's release cadence (but versioned independently — see §4.1).

---

## 4. Architecture

### 4.1 Suite versioning

Suite version follows semver. `suite_version` in `ConformanceReport` is the suite that produced the report. A protocol version is paired with a *minimum* suite version that is sufficient to test it. Newer suite versions test more thoroughly; older suite versions may not exercise newer protocol features.

### 4.2 Target abstraction

```python
class Target(Protocol):
    """A system under test (SUT). The suite never touches the SUT's internals."""
    base_url: str
    admin_token: AuthToken

    async def start(self) -> None: ...                 # for managed targets like docker
    async def stop(self) -> None: ...
    async def reset(self) -> None: ...                 # blank slate (for tests that need it)
    async def bus_call(self, capability: str, payload: dict) -> dict: ...
    async def event_subscribe(self, types: list[str]) -> AsyncIterator[Event]: ...
    async def http_get(self, path: str, headers: dict | None = None) -> Response: ...
    async def http_post(self, path: str, body: bytes, headers: dict | None = None) -> Response: ...
    async def ws_connect(self, path: str, subprotocol: str | None = None) -> WebSocket: ...
    async def capture_wire(self) -> WireCapture: ...   # for federation/tensor tests
```

Two concrete `Target` implementations ship:

- `LocalTarget`: SUT runs as a long-lived process accessible at a known URL. Simplest; used in CI against the reference implementation.
- `DockerTarget`: SUT runs in a docker container that the suite spawns. Useful for testing alternate implementations packaged as containers.

Authors of an alternate implementation supply their own `Target` subclass if needed.

### 4.3 Test format

Tests are plain `pytest` cases under `suites/`. They use the target as an injected fixture:

```python
# suites/core/identity/test_node_id_format.py

async def test_node_id_is_base32_no_pad(target: Target) -> None:
    r = await target.bus_call("identity.self.describe", {})
    node_id = r["node_id"]
    assert re.fullmatch(r"[A-Z2-7]+", node_id), "NodeID must be base32 with no padding"
    assert len(node_id) >= 52
```

Each test asserts at most one *spec requirement*. The test docstring names the spec section it covers; the runner uses this to produce traceability from `SectionResult.failures` back to the relevant module spec.

### 4.4 Wire vectors

For wire-format tests (federation manifest, tensor transport frame, token JWS envelope) the suite carries canonical byte vectors in `vectors/`. Tests assert that:

- The SUT, given a known input, produces a byte-equal output (after canonicalisation where applicable).
- The SUT, given a known byte vector, parses it without errors and produces the expected semantic content.

This catches subtle interop bugs — the kind of "we both speak JSON-with-tiny-differences" issue that has historically killed federated systems.

### 4.5 Report aggregation

After a run, `report.py`:

1. Collects per-test pass/fail/skip results.
2. Groups by suite path → SectionResult.
3. Computes `overall`:
   - `pass` if all `core/*` and all `services/*` sections passed (experimental and operability may fail without affecting `pass`).
   - `partial` if `core/*` passed but anything else failed.
   - `fail` if any `core/*` test failed.
   - `skipped` if no sections ran.
4. Signs the report with the SUT's identity (the SUT signs its own report — there is no external authority).
5. Emits `report.json` and a human-readable `report.html`.

### 4.6 Reproducibility

Every run produces a `run_manifest.json` containing:

- Suite version, suite git commit.
- Target type and configuration (without secrets).
- Random seed (suite seeds all RNGs deterministically for reproducibility).
- Test selection (which suites/tests were run vs skipped).
- Timestamps.

Replaying with the same manifest against the same SUT version must produce equivalent results modulo timestamps.

---

## 5. Required sections

A claim of "HearthNet-compliant at protocol version 3.0.0" requires passing **every test** under:

- `suites/core/identity/`
- `suites/core/transport/`
- `suites/core/bus/`
- `suites/core/events/`
- `suites/core/tokens/`
- `suites/core/files/`
- `suites/core/kb/` *(minimum: ingest, query)*
- `suites/core/llm/` *(minimum: chat capability, error handling)*

Plus passing the relevant *advertised-capability* sections under `suites/services/` for any service the implementation advertises. An implementation advertising `chat.thread.*` but not running `suites/services/chat/` is non-compliant by omission.

Federation is required for any implementation that advertises federation; otherwise it's optional. Experimental sections are *always* optional and `partial` is a valid honest outcome.

---

## 6. Behaviour

### 6.1 Pre-flight

Before running tests, the runner:

1. Confirms `target.start()` succeeded.
2. Calls `protocol.self_describe` and `protocol.version_list` to discover what to test.
3. Confirms `protocol_version` returned by the SUT is compatible with the suite's supported versions; if not, fails fast with `protocol_version_unsupported`.
4. Resets the SUT (`target.reset()`).
5. Loads vector files into memory.

### 6.2 Test isolation

Each test must be independent — order should not matter. Tests that need a clean slate request `target.reset()` in a fixture; tests that need shared state declare it via pytest fixtures with explicit scope.

Tests use synthetic identities and tokens generated per-test, never the real operator's keys.

### 6.3 Graceful skipping

A test that requires a capability not advertised by the SUT is *skipped*, not failed:

```python
@requires_capability("experimental.fedlearn.round.announce")
async def test_fedlearn_round_announce_signs_manifest(target: Target) -> None:
    ...
```

`requires_capability` queries `protocol.self_describe`. Skipped tests appear in the report as `skipped` with a reason. They never flip `overall` to `fail`.

### 6.4 Wire capture mode

For federation and tensor-transport sections, the runner may attach a `WireCapture` to record the raw bytes flowing between two SUT instances (or between an SUT and the suite's own simulator). The captured frames are checked against vectors and against the schema documented in the relevant cross-cutting spec.

Wire-capture mode requires the operator to have configured the SUT to log raw traffic to a known location (typically a Unix socket the suite reads). For SUTs that can't expose raw traffic, the suite falls back to behavioural assertions only and notes `partial` if wire vectors couldn't be verified.

### 6.5 Operability sections

`operability/` sections test resilience properties:

- `shutdown_clean`: send SIGTERM (or container stop); verify no events are lost, the audit chain (M31) verifies, and the SUT restarts cleanly.
- `restart_persistence`: data created before restart is queryable after restart.
- `observability`: standard event types fire as expected; X03 observability conformance.

### 6.6 Reporting failures

Each failure records:

- Spec section reference (e.g. `M14 §5.2 canonicalisation`).
- The actual observed value or behaviour.
- The expected value or behaviour.
- A reproduction recipe (capability call + payload, or wire vector identifier).

This is what makes a `partial` report useful: the failures are debuggable.

---

## 7. Configuration

```python
@dataclass(frozen=True)
class ConformanceConfig:
    target_kind:        Literal["local","docker","custom"] = "local"
    target_url:         str = "http://127.0.0.1:7900"
    target_admin_token: str | None = None         # acquired out-of-band
    docker_image:       str | None = None
    suite_filter:       tuple[str, ...] = ()      # glob patterns; empty = all required + advertised
    skip_experimental:  bool = False
    skip_operability:   bool = False
    wire_capture:       bool = False
    output_dir:         str = "./conformance-report"
    parallel:           int = 1                   # 1 by default to avoid test-isolation surprises
    seed:               int = 0xC0FFEE
```

A typical CI invocation:

```
python -m conformance.runner \
    --target=docker \
    --docker-image=hearthnet:latest \
    --output-dir=./report
```

---

## 8. Tests of the suite itself

The suite has its own tests, kept under `conformance/tests/`:

- `test_runner_smoke` — runs the suite against the reference impl, expects `overall=pass` for `core/*`.
- `test_skip_logic` — capabilities not advertised → tests skipped, not failed.
- `test_seed_deterministic` — given a seed, two consecutive runs produce identical reports modulo timestamps.
- `test_report_schema` — generated `ConformanceReport` validates against the schema in `protocol/`.
- `test_vector_integrity` — every file in `vectors/` parses with the canonical loader.
- `test_known_partial` — the reference impl with `experimental.*` disabled produces a `partial` report (because experimental tests skip, not fail) — verify that the `overall` calculation correctly produces `pass`, since experimental skips don't flip the bit.

---

## 9. Cross-references

- **M32 Protocol Standardisation** — consumes `ConformanceReport`; the suite is the source of "what conformance means".
- **Every module spec** — the suite's tests reference the spec section they verify.
- **X02 Event Log, X03 Observability** — operability tests assert on these.
- **X06 WebSocket, X08 Tensor Transport** — wire-capture vectors live in `vectors/`.

---

## 10. Open questions

1. **Adversarial tests.** v3.0 has minimal negative-path coverage in `core/`. A future suite version with a `security/` section that probes for known classes of mistakes (auth bypass, signature reuse, event-log forgery attempts) would be valuable. Out of scope for v3.0.

2. **Conformance for partial implementations.** The current model gates `pass` on all required `core/*` passing. A future tiered model (`HearthNet-Bronze` = identity + transport + bus only; `HearthNet-Silver` adds services; `HearthNet-Gold` adds federation) is appealing for low-resource implementations. Not in v3.0.

3. **Differential testing.** Once two implementations exist, running them side-by-side with the same input and asserting identical observable behaviour is the strongest interop test. The harness supports this in principle (two targets), but no tests in v3.0 actually use it because only one implementation exists.

4. **Vector generation.** Today vectors are hand-curated. Tooling to *regenerate* vectors from the reference implementation and detect drift would prevent test rot. Planned, not implemented.

5. **Reporting hub.** A public registry that collects published conformance reports from various implementations would help users assess interop status. Out of scope for the suite itself; M32's `protocol.registry.*` capabilities are the closest current analogue.

6. **Performance regression guardrails.** Not conformance, but obviously valuable. A separate X10 (TBD) may handle this.

7. **Long-haul tests.** Some bugs (memory leaks, slow drifts in audit chains) appear only after hours. The suite is built for short runs; a "soak mode" with `--duration=24h` would test these. Open.

8. **Federation interop with non-HearthNet systems.** Out of scope. The suite verifies HearthNet ↔ HearthNet federation only.

---

*Last updated: spec v3.0.*
