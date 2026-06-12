# HearthNet — Implementation Reference

**Purpose:** complete inventory of every file, class, method, and function across the spec set.
Use this as a coding checklist. For *why* and behaviour → follow the spec link on each entry.
For *what to call it* and *what it returns* → this document is normative.

**Spec set:** see [`00-OVERVIEW.md`](00-OVERVIEW.md), [`GLOSSARY.md`](GLOSSARY.md), [`CAPABILITY_CONTRACT.md`](CAPABILITY_CONTRACT.md).

---

## 0. Conventions (read first)

### 0.1 Type aliases — `hearthnet/types.py`

*Re-exported by every module that uses them. Never invent synonyms.* — [00-OVERVIEW §4.1](00-OVERVIEW.md)

| Alias | Underlying | Example |
|-------|------------|---------|
| `NodeID` | `str` | `"ed25519:7H4G-Y9KL-2P3M-X8QR"` (short) or full base64-url |
| `CommunityID` | `str` | full base64-url |
| `CapabilityName` | `str` | `"llm.chat"` |
| `Version` | `tuple[int, int]` | `(1, 0)` |
| `Lamport` | `int` | monotonic per community |
| `CID` | `str` | `"blake3:<hex>"` |
| `EventID` | `str` | ULID |
| `TraceID` | `str` | ULID |
| `SchemaHash` | `str` | `"blake3:<hex>"` |
| `WallClock` | `str` | `"2026-05-26T08:14:22Z"` |
| `Signature` | `str` | `"ed25519:<base64-url-nopad>"` |
| `Topic` | `str` | `"marketplace.post.created"` |
| `ErrorCode` | `Literal[...]` | see [CONTRACT §9](CAPABILITY_CONTRACT.md) |
| `TrustLevel` | `Literal["unknown","member","trusted","anchor"]` | |
| `Profile` | `Literal["anchor","hearth","spark","bridge"]` | |
| `Stability` | `Literal["experimental","beta","stable"]` | |
| `Mode` | `Literal["online","degraded","offline"]` | emergency state |
| `Category` | `Literal["offer","request","info","emergency"]` | marketplace post |
| `EventType` | `Literal[...]` | 19 values; see [X02 §3.1](cross-cutting/X02-events.md) |

### 0.2 Constants — `hearthnet/constants.py`

Hardcoded; never configurable. Complete list in [GLOSSARY.md §Defaults](GLOSSARY.md).

`MANIFEST_TTL_SECONDS=30`, `MANIFEST_REPUBLISH_INTERVAL_SECONDS=20`, `DISCOVERY_UDP_INTERVAL_SECONDS` (5 active / 30 stable), `EMERGENCY_PROBE_INTERVAL_ONLINE=10`, `EMERGENCY_PROBE_INTERVAL_OFFLINE=2`, `EMERGENCY_PROBE_TIMEOUT_SECONDS=2`, `EMERGENCY_TRANSITION_DEBOUNCE_SECONDS=30`, `CONNECTION_IDLE_SECONDS=60`, `RECONNECT_BACKOFF_CAP_SECONDS=30`, `STREAM_WINDOW_FRAMES=16`, `STREAM_ACK_INTERVAL_FRAMES=8`, `STREAM_ACK_TIMEOUT_SECONDS=5`, `RPC_DEFAULT_TIMEOUT_SECONDS=30`, `LLM_GENERATION_DEFAULT_TIMEOUT_SECONDS=120`, `CHUNK_SIZE_BYTES=262144`, `BLOB_GC_DISK_THRESHOLD=0.80`, `RAG_CHUNK_TOKENS=1000`, `RAG_CHUNK_OVERLAP_TOKENS=200`, `RAG_DEFAULT_K=5`, `RAG_MAX_K=20`, `HEALTH_WINDOW_CALLS=100`, `HEALTH_QUARANTINE_THRESHOLD=0.5`, `HEALTH_QUARANTINE_SECONDS=60`, `RATE_LIMIT_SOFT_RPS_PER_CAP=10`, `RATE_LIMIT_HARD_RPS_PER_CAP=100`, `RATE_LIMIT_SOFT_RPS_TOTAL=100`, `RATE_LIMIT_HARD_RPS_TOTAL=1000`, `EVENT_LOG_RETENTION_DAYS=30`, `SNAPSHOT_LAG_LAMPORT=1000`, `TRACE_RING_BUFFER=10000`, `LOG_RETENTION_DAYS=14`.

### 0.3 Naming rules

- Functions: `snake_case`, verb-first
- Classes: `PascalCase`, noun
- Constants: `SCREAMING_SNAKE`
- Async I/O: `async def`; no `async_` prefix on names
- Protocols: `PascalCase` ending in capability noun (`LlmBackend`, `Service`)
- Private: leading underscore (`_compute_canonical_json`)

### 0.4 Universal error code → wire code mapping

| Domain exception | Wire `ErrorCode` | HTTP |
|------------------|------------------|------|
| `IdentityError("invalid_signature")` | `invalid_signature` | 401 |
| `IdentityError("expired")` | `expired` | 410 |
| `BusError("schema_mismatch")` | `schema_mismatch` | 400 |
| `BusError("not_found")` | `not_found` | 404 |
| `BusError("capacity_exceeded")` | `capacity_exceeded` | 429 |
| `BusError("quarantined" / "partition")` | `partition` | 503 |
| `BusError("timeout")` | `timeout` | 408 |
| `EventLogError("invalid_signature")` | `invalid_signature` | — (internal) |
| `BlobError("not_found")` | `not_found` | 404 |
| `BlobError("hash_mismatch")` | `bad_request` | 400 |
| `BlobError("disk_full")` | `capacity_exceeded` | 429 |
| `OnboardingError(*)` | — (local UI only) | — |
| `ConfigError(*)` | — (startup) | — |

---

## 1. X04 — Configuration

**Spec:** [`cross-cutting/X04-config.md`](cross-cutting/X04-config.md) · **Path:** `hearthnet/config.py` + `hearthnet/constants.py`

### `hearthnet/config.py`

#### Dataclasses (all `@dataclass(frozen=True)`)

`IdentityConfig` — §3:
- `keys_dir: Path`
- `auto_generate: bool = True`

`CommunityConfig` — §3:
- `community_id: Optional[str] = None`
- `state_dir: Path = Path()`

`TransportConfig` — §3:
- `host: str = "0.0.0.0"`
- `port: int = 7080`
- `tls_cert: Optional[Path] = None`
- `tls_key: Optional[Path] = None`

`DiscoveryConfig` — §3:
- `mdns_enabled: bool = True`
- `udp_enabled: bool = True`
- `udp_multicast_group: str = "239.255.42.42"`
- `udp_port: int = 42424`
- `relay_urls: list[str] = []`

`BusConfig` — §3:
- `prefer_local: bool = True`
- `local_load_threshold: float = 0.80`

`LlmBackendConfig` — §3:
- `name: str` — one of `"llama_cpp" | "ollama" | "lmstudio" | "vllm" | "hf_api" | "anthropic_api" | "nemotron" | "openbmb"`
- `url: Optional[str] = None`
- `model: Optional[str] = None`
- `api_key_env: Optional[str] = None`

`LlmConfig` — §3:
- `backends: list[LlmBackendConfig] = []`

`EmbeddingConfig` — §3:
- `model: str = "BAAI/bge-small-en-v1.5"`
- `device: str = "auto"`

`RagConfig` — §3:
- `enabled: bool = True`
- `corpora_dir: Path = Path()`

`FileConfig` — §3:
- `blobs_dir: Path = Path()`
- `gc_threshold: float = 0.80`

`MarketConfig` — §3:
- `enabled: bool = True`
- `default_ttl_seconds: int = 604800`
- `max_ttl_seconds: int = 2592000`

`ChatConfig` — §3:
- `enabled: bool = True`
- `store_and_forward: bool = True`

`EmergencyConfig` — §3:
- `probe_targets: list[str] = ["1.1.1.1","8.8.8.8","cloudflare.com","quad9.net"]`

`UiConfig` — §3:
- `host: str = "127.0.0.1"`
- `port: int = 7860`
- `launch_browser: bool = True`

`ObservabilityConfig` — §3 (+ trackio addition):
- `log_level: str = "info"`
- `log_dir: Path = Path()`
- `metrics_enabled: bool = True`
- `otlp_endpoint: Optional[str] = None`
- `trackio_project: Optional[str] = None` — local trackio project name; enables trackio exporter when set
- `trackio_space: Optional[str] = None` — HF Space URL to mirror trackio runs to; optional

`Config` — §3:
- holds one of each of the above as named attributes

#### Functions

- `load(path: Path | None = None) -> Config` — §4. Read TOML, apply defaults, resolve paths, validate. Raises `ConfigError`.
- `default_config() -> Config` — §4. All-defaults Config.
- `save(config: Config, path: Path | None = None) -> None` — §4. Atomic TOML write.
- `resolve_paths(config: Config) -> Config` — §4. Resolve empty `Path()` to XDG locations. Idempotent.
- `validate(config: Config) -> None` — §4. Cross-field checks; raises `ConfigError`.

#### Exception

`ConfigError(Exception)` — §4:
- `__init__(code: str, **details)`
- `code: str`
- `details: dict`

### `hearthnet/constants.py`

Module-level constants from [GLOSSARY.md §Defaults](GLOSSARY.md). No classes; just `NAME = value` lines.

---

## 2. X03 — Observability

**Spec:** [`cross-cutting/X03-observability.md`](cross-cutting/X03-observability.md) · **Path:** `hearthnet/observability/`

### `hearthnet/observability/logging.py` — §3

#### Functions

- `configure(config: ObservabilityConfig) -> None` — install handlers + rotation; idempotent.
- `get_logger(name: str) -> logging.Logger` — JSON-formatted logger.

#### Class

`JsonFormatter(logging.Formatter)` — §3.1:
- `format(record: LogRecord) -> str` — emit `{"ts","level","logger","msg",**extras}`.

`RateLimitedLogger` — §3.2 (internal wrapper):
- `__init__(logger: Logger, per_key_seconds: float = 1.0)`
- `info(msg: str, key: str, **extras) -> None`
- `warning(msg: str, key: str, **extras) -> None`

### `hearthnet/observability/metrics.py` — §4

#### Functions

- `configure(config: ObservabilityConfig) -> None` — set up registries, start `/metrics` endpoint.
- `counter(name: str, doc: str, labels: list[str] = []) -> Counter`
- `histogram(name: str, doc: str, labels: list[str] = [], buckets: list[float] | None = None) -> Histogram`
- `gauge(name: str, doc: str, labels: list[str] = []) -> Gauge`
- `disabled() -> bool` — true when metrics are off.

#### Standard metric set — §4.2

Pre-registered at startup with these exact names:
`hearthnet_requests_total{capability,result}`, `hearthnet_request_duration_ms{capability,quantile}`, `hearthnet_active_streams{capability}`, `hearthnet_nodes_online{community}`, `hearthnet_event_log_size{community}`, `hearthnet_event_log_lamport_head{community}`, `hearthnet_emergency_mode{state}`, `hearthnet_blob_storage_bytes`, `hearthnet_llm_tokens_generated_total{model,backend}`, `hearthnet_llm_concurrent{model}`, `hearthnet_capability_health_success_rate{capability,node}`, `hearthnet_rate_limited_total{capability,reason}`, `hearthnet_signature_failures_total{reason}`, `hearthnet_quarantines_total`.

#### Trackio integration (new) — §4.4

`TrackioExporter` — optional. Activated when `config.observability.trackio_project` is set.
- `__init__(project: str, space: str | None = None)` — opens a trackio run.
- `record_call(capability: str, model: str | None, latency_ms: float, tokens_in: int | None, tokens_out: int | None, result: str) -> None` — logs one inference call as a step in the run.
- `record_topology_snapshot(snapshot: TopologySnapshot) -> None` — periodic mesh health log.
- `close() -> None`

Use trackio when you want a Gradio-native dashboard for run/inference history (alternative or complement to Prometheus). Bridged into `TraceHook.on_call_end` when active.

### `hearthnet/observability/tracing.py` — §5

#### Dataclasses

`Trace` — §5.1:
- `trace_id: str` (ULID)
- `capability: str`
- `started_at: float`
- `spans: list[Span]`

`Span` — §5.1:
- `name: str`
- `started_at: float`
- `ended_at: float | None`
- `extras: dict`

#### Functions

- `new_trace(capability: str) -> Trace` — open a new trace, attach to current task.
- `current_trace() -> Trace | None`
- `attach(trace: Trace) -> None`
- `detach() -> None` — close the current trace, push to ring buffer.
- `span(name: str, **extras) -> AbstractAsyncContextManager[Span]` — open a sub-span.
- `get_recent(n: int = 100) -> list[Trace]` — read from ring buffer (size `TRACE_RING_BUFFER`).

### `hearthnet/observability/doctor.py` — §6

#### Dataclass

`CheckResult` — §6.1:
- `name: str`
- `ok: bool`
- `detail: str`
- `fix: str | None`

#### Functions

- `register(name: str, check: Callable[[Config, CapabilityBus], CheckResult]) -> None`
- `run_all(config: Config, bus: CapabilityBus) -> list[CheckResult]`
- `run_one(name: str, config: Config, bus: CapabilityBus) -> CheckResult`

#### Standard checks (registered at startup) — §6.2

`keys_present`, `keys_loadable`, `community_present`, `event_log_writable`, `mdns_socket`, `udp_multicast`, `transport_port`, `at_least_one_capability`, `disk_space`, `clock_sanity`, `llm_backend_reachable`, `recent_error_rate`.

---

## 3. X02 — Events

**Spec:** [`cross-cutting/X02-events.md`](cross-cutting/X02-events.md) · **Path:** `hearthnet/events/`

### `hearthnet/events/types.py` — §3.1

`EventType` — Literal of 19 strings, exactly:
`community.created`, `community.member.invited`, `community.member.joined`, `community.member.revoked`, `community.member.promoted`, `community.member.demoted`, `community.policy.updated`, `node.manifest.updated`, `market.post.created`, `market.post.updated`, `market.post.expired`, `chat.message.sent`, `chat.message.delivered`, `chat.message.read`, `file.cid.advertised`, `file.cid.unpinned`, `rag.document.ingested`, `federation.peer.added`, `federation.peer.removed`.

`Event` *(frozen dataclass)*:
- `schema_version: int`
- `event_id: str`
- `lamport: int`
- `wall_clock: str`
- `community_id: str`
- `author: str`
- `event_type: EventType`
- `data: dict`
- `signature: str`

### `hearthnet/events/lamport.py` — §3.2

`LamportClock`:
- `__init__(conn: sqlite3.Connection, community_id: str)` — load current value.
- `current: int` *(property)*
- `tick_for_send() -> int` — increment + persist; returns new value.
- `observe(received_lamport: int) -> None` — `max(current, received) + 1`.

### `hearthnet/events/log.py` — §3.3

`EventLog`:
- `__init__(db_path: Path, community_id: str)` — open/create SQLite (WAL); apply schema.
- `append_local(event_type: EventType, data: dict, author_kp: KeyPair) -> Event` — mint, sign, persist, fan out.
- `append_received(event: Event) -> bool` — verify, persist if new. Returns True if new.
- `head() -> int` — highest Lamport.
- `get(event_id: str) -> Event | None`
- `replay(*, since_lamport: int = 0, event_types: list[EventType] | None = None, limit: int | None = None) -> Iterator[Event]`
- `heads_by_type() -> dict[EventType, int]`
- `subscribe(event_types: list[EventType] | None = None) -> AsyncIterator[Event]`

`EventLogError(Exception)`:
- `code in {"invalid_signature","out_of_order","unknown_author","revoked_author","schema_unknown","db_corrupt"}`

### `hearthnet/events/replay.py` — §3.4

`MaterialisedView` *(Protocol)*:
- `reset() -> None`
- `apply(event: Event) -> None`
- `snapshot_state() -> dict`
- `restore_state(state: dict) -> None`

`ReplayEngine`:
- `__init__(log: EventLog)`
- `register(name: str, view: MaterialisedView, event_types: list[EventType]) -> None`
- `rebuild(view_name: str, from_lamport: int = 0) -> None`
- `rebuild_all() -> None`
- `on_event(event: Event) -> None` — wired from `EventLog`.

### `hearthnet/events/snapshot.py` — §3.5

`Snapshot` *(frozen dataclass)*:
- `schema_version: int`
- `community_id: str`
- `lamport: int`
- `wall_clock: str`
- `state: dict`
- `covers_events_up_to: int`
- `signature: str`

`SnapshotStore`:
- `__init__(dir_path: Path, community_id: str)`
- `latest() -> Snapshot | None`
- `write(snap: Snapshot) -> None` — atomic.
- `list() -> list[int]`
- `prune(keep_last_n: int = 7) -> None`

Free functions:
- `build_snapshot(log: EventLog, engine: ReplayEngine, signing_kp: KeyPair, at_lamport: int | None = None) -> Snapshot`
- `restore_from_snapshot(snap: Snapshot, engine: ReplayEngine, log: EventLog) -> None`

### `hearthnet/events/sync.py` — §3.6

`HeadsReport` *(frozen dataclass)*:
- `community_id: str`
- `heads_by_type: dict[EventType, int]`
- `head: int`

`SyncResult` *(frozen dataclass)*:
- `sent_count: int`
- `received_count: int`
- `duration_ms: int`

`SyncClient`:
- `__init__(log: EventLog, transport_client: HttpClient)`
- `sync_with(peer_endpoint: Endpoint) -> SyncResult` *(async)*
- `run_round(peer_registry: PeerRegistry) -> list[SyncResult]` *(async)* — sync against all known peers.

`SyncServer`:
- `__init__(log: EventLog)`
- `serve_heads() -> HeadsReport` *(async)*
- `serve_events(events: list[Event]) -> dict` *(async)*

---

## 4. X01 — Transport

**Spec:** [`cross-cutting/X01-transport.md`](cross-cutting/X01-transport.md) · **Path:** `hearthnet/transport/`

### `hearthnet/transport/server.py` — §3

`HttpServer`:
- `__init__(config: TransportConfig, kp: KeyPair, bus: CapabilityBus, event_sync: SyncServer, community_manifest_provider: Callable[[], CommunityManifest])`
- `app() -> FastAPI` — for tests.
- `run() -> None` *(async)* — block, serve.
- `shutdown() -> None` *(async)*

#### Mounted endpoints — §3.2

`POST /bus/v1/call`, `GET /manifest`, `GET /community/manifest`, `GET /sync/v1/heads`, `POST /sync/v1/events`, `GET /pubsub/v1/subscribe`, `GET /health`, `GET /ready`, `GET /metrics`, `GET /trace/recent`.

`PubSubServer` — §8:
- `publish(topic: str, payload: dict) -> None` *(async)*
- `subscribe(topic: str, *, last_seq: int = 0, timeout_seconds: float = 30) -> dict` *(async)* — long-poll.

### `hearthnet/transport/client.py` — §5

`HttpClient`:
- `__init__(kp: KeyPair, node_id: str, community_id: str, pinned_certs: PinnedCerts, timeout_default_seconds: float = RPC_DEFAULT_TIMEOUT_SECONDS)`
- `call(peer: Endpoint, capability: str, version: str, body: dict, *, trace_id: str | None = None, timeout_seconds: float | None = None) -> dict` *(async)* — signed RPC.
- `stream(peer: Endpoint, capability: str, version: str, body: dict, *, trace_id: str | None = None, cancel: asyncio.Event | None = None) -> AsyncIterator[Frame]` — signed stream.
- `close() -> None` *(async)*

`CallError(Exception)`:
- `code: ErrorCode`
- `message: str`
- `retry_after_ms: int | None`
- `alt_capabilities: list[str]`
- `alt_nodes: list[str]`

### `hearthnet/transport/streams.py` — §6

`Frame` *(frozen dataclass)*:
- `event: str` — `"token" | "chunk" | "progress" | "ack" | "done" | "error" | "manifest" | "ready" | "tool_call_delta"`
- `data: dict`
- `seq: int`

`SseWriter`:
- `__init__(response: StreamingResponse)`
- `emit(event: str, data: dict) -> None` *(async)*
- `emit_token(token: dict) -> None` *(async)*
- `emit_progress(current: int, total: int, stage: str) -> None` *(async)*
- `emit_error(code: ErrorCode, **kwargs) -> None` *(async)*
- `emit_done(**meta) -> None` *(async)*
- `emit_ack(upto: int) -> None` *(async)*
- `cancelled: bool` *(property)*

`SseReader`:
- `__aiter__() -> AsyncIterator[Frame]`
- `cancel() -> None` *(async)*

### `hearthnet/transport/backpressure.py` — §6.3

`FlowControl`:
- `__init__(window: int = STREAM_WINDOW_FRAMES, ack_interval: int = STREAM_ACK_INTERVAL_FRAMES)`
- `window_used: int` *(property)*
- `send() -> None` *(async)* — await if window full.
- `ack(upto: int) -> None`
- `needs_ack: bool` *(property)*

### `hearthnet/transport/tls.py` — §4

`PinnedCerts`:
- `__init__(db_path: Path)`
- `record(node_id: str, fingerprint: bytes) -> None`
- `expected(node_id: str) -> bytes | None`
- `verify(node_id: str, presented: bytes) -> bool`

### `hearthnet/transport/__init__.py` — §7

`RateCheck` *(frozen dataclass)*:
- `allowed: bool`
- `soft_exceeded: bool`
- `retry_after_ms: int`

`RateLimiter`:
- `__init__(config: TransportConfig)`
- `check(peer_node_id: str, capability: str) -> RateCheck`

---

## 5. M01 — Identity & Manifests

**Spec:** [`modules/M01-identity.md`](modules/M01-identity.md) · **Path:** `hearthnet/identity/`

### `hearthnet/identity/keys.py` — §3.1

#### Class

`KeyPair` *(frozen dataclass)*:
- `signing_key: nacl.signing.SigningKey`
- `verify_key: nacl.signing.VerifyKey`
- `node_id_full: str`
- `node_id_short: str`
- `sign(payload: dict) -> dict` — returns `payload` + `signature` field.
- `sign_bytes(data: bytes) -> Signature`

#### Functions

- `generate() -> KeyPair`
- `load(keys_dir: Path) -> KeyPair` — raises `IdentityError("keys_missing"|"keys_invalid"|"keys_permissions")`.
- `load_or_generate(keys_dir: Path) -> KeyPair`
- `save(kp: KeyPair, keys_dir: Path) -> None` — 0600 perms.
- `short_node_id(verify_key_bytes: bytes) -> str` — `"ed25519:XXXX-XXXX-XXXX-XXXX"`.
- `full_node_id(verify_key_bytes: bytes) -> str` — `"ed25519:<base64-url-nopad>"`.
- `parse_node_id(node_id: str) -> bytes` — accepts only full form.
- `verify_key_from_full(node_id_full: str) -> VerifyKey`
- `canonical_json(obj: Any) -> bytes` — sorted, no whitespace, no trailing zeros, UTF-8.
- `sign_payload(payload: dict, kp: KeyPair) -> dict`
- `verify_payload(payload: dict, vk: VerifyKey) -> bool`
- `verify_payload_with_node_id(payload: dict, expected_node_id_full: str) -> bool`
- `generate_self_signed_cert(kp: KeyPair, host: str = "0.0.0.0") -> tuple[bytes, bytes]` — `(cert_pem, key_pem)`, 10-year validity.

#### Exception

`IdentityError(Exception)`:
- `code in {"keys_missing","keys_invalid","keys_permissions","bad_node_id","sign_failed","verify_failed","bad_manifest","expired","invalid_signature"}`

### `hearthnet/identity/manifest.py` — §3.2

#### Dataclasses

`Endpoint` *(frozen)*: `transport: str`, `host: str`, `port: int`.

`HardwareSpec` *(frozen)*: `gpu: str | None`, `vram_gb: float`, `ram_gb: float`, `cpu_cores: int`, `disk_free_gb: float`.

`CapabilitySpec` *(frozen)* — subset of `CapabilityDescriptor` for manifest embedding:
- `name: str`, `version: str`, `stability: str`, `schema_hash: str`, `params: dict`, `max_concurrent: int`.

`NodeManifest` *(frozen)*:
- `version: int`, `contract_version: str`, `node_id: str`, `display_name: str`, `community_id: str`, `profile: str`, `endpoints: list[Endpoint]`, `hardware: HardwareSpec`, `capabilities: list[CapabilitySpec]`, `uptime_seconds: int`, `load: dict`, `issued_at: str`, `expires_at: str`, `signature: str`.
- `as_dict() -> dict`
- `is_expired(now: datetime | None = None) -> bool`

`CommunityPolicy` *(frozen)*:
- `min_signatures_to_invite: int`
- `min_signatures_to_demote: int`
- `min_signatures_to_revoke: int`
- `capability_token_ttl_seconds: int`
- `federation_enabled: bool`
- `default_member_can_invite: bool`

`CommunityMember` *(frozen)*: `node_id: str`, `level: TrustLevel`, `added_at: str`, `added_by: str`.

`RevokedEntry` *(frozen)*: `node_id: str`, `revoked_at: str`.

`CommunityManifest` *(frozen)*:
- `version: int`, `community_id: str`, `name: str`, `root_key: str`, `created_at: str`, `lamport_at_creation: int`, `policy: CommunityPolicy`, `members: list[CommunityMember]`, `revoked: list[RevokedEntry]`, `head_lamport: int`, `signature: str`.
- `is_member(node_id: str) -> bool`
- `level_of(node_id: str) -> TrustLevel | None`
- `is_revoked(node_id: str) -> bool`

#### Functions

- `build_node_manifest(kp: KeyPair, community_id: str, display_name: str, profile: str, endpoints: list[Endpoint], hardware: HardwareSpec, capabilities: list[CapabilitySpec], uptime_seconds: int, load: dict) -> NodeManifest`
- `parse_node_manifest(blob: bytes | dict) -> NodeManifest`
- `verify_node_manifest(manifest: NodeManifest, *, now: datetime | None = None) -> None`
- `build_community_manifest(root_kp: KeyPair, name: str, policy: CommunityPolicy) -> CommunityManifest`
- `regenerate_community_manifest_from_state(materialised_state: dict, signing_kp: KeyPair) -> CommunityManifest`
- `parse_community_manifest(blob: bytes | dict) -> CommunityManifest`
- `verify_community_manifest(cm: CommunityManifest) -> None`
- `load_or_regenerate(state_dir: Path, signing_kp: KeyPair | None = None) -> CommunityManifest` — convenience used by `node.py`.

### `hearthnet/identity/tokens.py` — §3.3 *(Phase 2; stub in MVP)*

`CapabilityToken` *(frozen)*: `issuer: str`, `subject: str`, `capability: str`, `issued_at: str`, `expires_at: str`, `nonce: str`, `signature: str`.

Functions (stubs):
- `issue_token(issuer_kp: KeyPair, subject_node_id: str, capability: str, ttl_seconds: int = 86400) -> CapabilityToken`
- `verify_token(token: CapabilityToken, expected_issuer: str) -> None`

---

## 6. M02 — Discovery

**Spec:** [`modules/M02-discovery.md`](modules/M02-discovery.md) · **Path:** `hearthnet/discovery/`

### `hearthnet/discovery/peers.py` — §3.1

`PeerRecord` *(dataclass)*:
- `node_id: str` (short), `node_id_full: str`, `display_name: str`, `community_id: str`, `profile: Profile`, `endpoints: list[Endpoint]`, `manifest: NodeManifest | None`, `last_seen: float`, `rtt_ms: float | None`, `source: str` (`"mdns"|"udp"|"relay"`).

`PeerEvent` *(frozen)*: `kind: str` (`"added"|"removed"|"updated"`), `peer: PeerRecord`.

`PeerRegistry`:
- `__init__(our_node_id_full: str, community_id: str)`
- `upsert(record: PeerRecord) -> bool` — True if new.
- `remove(node_id_full: str) -> bool`
- `get(node_id_full: str) -> PeerRecord | None`
- `all() -> list[PeerRecord]`
- `for_community(community_id: str) -> list[PeerRecord]`
- `prune_stale(max_age_seconds: int = 90) -> int`
- `subscribe() -> AsyncIterator[PeerEvent]`
- `set_pruning_aggressive(enabled: bool) -> None` — toggled by M09; uses 30s when on, 90s when off.

### `hearthnet/discovery/mdns.py` — §3.2

`MdnsAnnouncer`:
- `__init__(kp: KeyPair, node_id_short: str, display_name: str, community_id_short: str, profile: Profile, port: int, capabilities_names: list[str], manifest_url: str)`
- `start() -> None` *(async)*
- `stop() -> None` *(async)*
- `update(*, capabilities_names: list[str] | None = None) -> None`

`MdnsBrowser`:
- `__init__(registry: PeerRegistry, our_community_id: str)`
- `start() -> None` *(async)*
- `stop() -> None` *(async)*

### `hearthnet/discovery/udp.py` — §3.4

`UdpAnnouncer`:
- `__init__(kp: KeyPair, registry: PeerRegistry, node_id_short: str, community_id_short: str, port: int, capabilities_names: list[str], multicast_group: str = "239.255.42.42", multicast_port: int = 42424)`
- `run() -> None` *(async)*

`UdpListener`:
- `__init__(registry: PeerRegistry, our_community_id: str)`
- `run() -> None` *(async)*

### `hearthnet/discovery/relay.py` *(Phase 2 stub)*

`InternetRelayClient` — not implemented in MVP. Reserved.

#### Exception

`DiscoveryError(Exception)`:
- `code in {"socket_in_use","mdns_unavailable","manifest_fetch_failed","manifest_invalid"}`

---

## 7. M03 — Capability Bus

**Spec:** [`modules/M03-bus.md`](modules/M03-bus.md) · **Path:** `hearthnet/bus/`

### `hearthnet/bus/capability.py` — §3.1

`CapabilityDescriptor` *(frozen dataclass)*:
- `name: CapabilityName`, `version: Version`, `stability: Stability`, `request_schema: dict`, `response_schema: dict | None`, `stream_schema: dict | None`, `params: dict`, `max_concurrent: int`, `trust_required: str` (`"member"|"trusted"|"anchor"|"self"`), `timeout_seconds: int`, `idempotent: bool`.
- `version_str -> str` *(property)*
- `schema_hash() -> str` — BLAKE3 of canonical-JSON of `{name, version, request_schema, response_schema, stream_schema}`.

`CapabilityEntry` *(dataclass)*:
- `node_id: str`, `descriptor: CapabilityDescriptor`, `is_local: bool`, `handler: Callable | None`, `endpoint: Endpoint | None`, `in_flight: int`, `last_seen: float`, `p50_latency_ms: float`, `p99_latency_ms: float`, `success_rate: float`, `quarantined_until: float`, `sticky_sessions: set[str]`.

`RouteRequest` *(frozen dataclass)*:
- `capability: CapabilityName`, `version_req: Version`, `body: dict`, `caller: str`, `trace_id: str`, `session_id: str | None`, `deadline_ms: int`, `stream: bool`.

`ParamsPredicate` — type alias: `Callable[[dict, dict], bool]`.

### `hearthnet/bus/registry.py` — §3.2

`Diff` *(frozen dataclass)*: `added`, `removed`, `updated` — each `list[CapabilityEntry]`.

`RegistryEvent` *(frozen dataclass)*: `kind: str` (`"added"|"removed"|"updated"`), `entry: CapabilityEntry`.

`Registry`:
- `__init__(our_node_id: str)`
- `register_local(descriptor: CapabilityDescriptor, handler: Callable, params_compatible: ParamsPredicate | None = None) -> None`
- `deregister_local(name: CapabilityName, version: Version) -> None`
- `update_from_peer_manifest(peer: PeerRecord, manifest: NodeManifest) -> Diff`
- `remove_peer(node_id: str) -> int`
- `find(name: CapabilityName, version_req: Version, params_filter: Callable[[dict], bool] | None = None) -> list[CapabilityEntry]`
- `entry(node_id: str, name: CapabilityName, version: Version) -> CapabilityEntry | None`
- `all_local() -> list[CapabilityEntry]`
- `all() -> list[CapabilityEntry]`
- `subscribe() -> AsyncIterator[RegistryEvent]`

### `hearthnet/bus/health.py` — §3.3

`HealthTracker`:
- `__init__(window: int = HEALTH_WINDOW_CALLS)`
- `record(entry: CapabilityEntry, *, success: bool, latency_ms: float) -> None`
- `is_quarantined(entry: CapabilityEntry) -> bool`
- `reset(entry: CapabilityEntry) -> None`

### `hearthnet/bus/schema.py` — §3.4

`SchemaValidator`:
- `__init__()`
- `validate_request(descriptor: CapabilityDescriptor, body: dict) -> None`
- `validate_response(descriptor: CapabilityDescriptor, body: dict) -> None`
- `validate_stream_frame(descriptor: CapabilityDescriptor, frame: dict) -> None`

Free function:
- `compute_schema_hash(descriptor_partial: dict) -> str` — `"blake3:<hex>"`. See [CONTRACT §11](CAPABILITY_CONTRACT.md).

### `hearthnet/bus/router.py` — §3.5

`Router`:
- `__init__(registry: Registry, config: BusConfig, our_node_id: str)`
- `route(req: RouteRequest) -> CapabilityEntry | None` — scoring algorithm; see §5.4.
- `route_sticky(req: RouteRequest) -> CapabilityEntry | None`
- `release_session(session_id: str) -> None`

### `hearthnet/bus/trace.py` — §3.6

`CallTraceEvent` *(frozen dataclass)*:
- `ts: str`, `trace_id: str`, `capability: CapabilityName`, `version: str`, `from_node: str`, `to_node: str`, `is_local: bool`, `result: str`, `ms: float`, `tokens_in: int | None`, `tokens_out: int | None`, `bytes_in: int`, `bytes_out: int`.

`TraceHook`:
- `__init__()`
- `on_call_start(req: RouteRequest, entry: CapabilityEntry) -> None`
- `on_call_end(req: RouteRequest, entry: CapabilityEntry, *, result: str, latency_ms: float, bytes_in: int, bytes_out: int, tokens_in: int | None = None, tokens_out: int | None = None) -> None`

### `hearthnet/bus/__init__.py` — §3.7

`TopologySnapshot` *(frozen dataclass)*:
- `our_node_id: str`, `peers: list[PeerRecord]`, `capabilities_local: list[CapabilityEntry]`, `capabilities_remote: list[CapabilityEntry]`, `in_flight_total: int`.

`CapabilityBus`:
- `__init__(node_id_full: str, community_id: str, config: BusConfig, transport_client: HttpClient, community_manifest_provider: Callable[[], CommunityManifest])`
- attributes: `registry`, `health`, `schema`, `router`, `trace`
- `register_service(service: Service) -> None`
- `register_capability(descriptor: CapabilityDescriptor, handler: Callable, params_compatible: ParamsPredicate | None = None) -> None`
- `handle_call(req: RouteRequest) -> dict | AsyncIterator[dict]` *(async)*
- `call(capability: CapabilityName, version_req: Version, body: dict, *, session_id: str | None = None, timeout_seconds: float | None = None) -> dict` *(async)*
- `stream(capability: CapabilityName, version_req: Version, body: dict, *, session_id: str | None = None) -> AsyncIterator[Frame]`
- `on_peer_added(peer: PeerRecord) -> None`
- `on_peer_updated(peer: PeerRecord) -> None`
- `on_peer_removed(node_id: str) -> None`
- `topology_snapshot() -> TopologySnapshot`
- `recent_traces(n: int = 50) -> list[CallTraceEvent]`
- `stats() -> dict`

`BusError(Exception)`:
- `code in {"schema_invalid","namespace_violation","schema_mismatch","not_found","capacity_exceeded","quarantined","partition","timeout","internal_error"}`

### `hearthnet/services/base.py` — M03 §4

`Service` *(Protocol)*:
- `name: str`
- `version: str`
- `capabilities() -> list[tuple[CapabilityDescriptor, Callable, ParamsPredicate]]`
- `start() -> None` *(async)*
- `stop() -> None` *(async)*
- `health() -> dict`

---

## 8. M11 — Embedding Service

**Spec:** [`modules/M11-embedding.md`](modules/M11-embedding.md) · **Path:** `hearthnet/services/embedding/`

### `hearthnet/services/embedding/backends.py` — §3.1

`EmbeddingBackend` *(Protocol)*:
- attrs: `name: str`, `model: str`, `dim: int`, `max_input: int`
- `embed(texts: list[str], *, normalize: bool = True) -> list[list[float]]` *(async)*
- `warm() -> None` *(async)*
- `close() -> None` *(async)*
- `health() -> dict`

`SentenceTransformerBackend`:
- `__init__(model: str, device: str = "auto")` — `device` ∈ `{"auto","cpu","cuda"}`.
- all `EmbeddingBackend` methods.

### `hearthnet/services/embedding/service.py` — §3.2

`EmbeddingService` *(implements `Service`)*:
- `name = "embedding"`, `version = "1.0"`
- `__init__(config: EmbeddingConfig)`
- `capabilities() -> [...]` — registers `embed.text@1.0`.
- `start()`, `stop()`, `health()` *(async)*
- `handle_embed_text(req: RouteRequest) -> dict` *(async)* — implements [CONTRACT §4.3](CAPABILITY_CONTRACT.md).

#### Capability params predicate

```python
def params_compatible(offered: dict, requested: dict) -> bool:
    return requested.get("model") == offered.get("model")
```

---

## 9. M04 — LLM Service

**Spec:** [`modules/M04-llm.md`](modules/M04-llm.md) · **Path:** `hearthnet/services/llm/`

### `hearthnet/services/llm/backends/base.py` — §3.1

`Token` *(frozen dataclass)*: `text: str`, `logprob: float | None`, `stop: bool`.

`ChatResult` *(frozen dataclass)*: `text: str`, `tokens_in: int`, `tokens_out: int`, `stop_reason: str`, `ms: int`.

`BackendModel` *(frozen dataclass)*: `name: str`, `quant: str`, `ctx_max: int`, `modalities: list[str]`, `requires_internet: bool`.

`LlmBackend` *(Protocol)*:
- attrs: `name: str`, `models: list[BackendModel]`
- `warm(model: str) -> None` *(async)*
- `close() -> None` *(async)*
- `chat(*, model: str, messages: list[dict], max_tokens: int = 1024, temperature: float = 0.7, top_p: float = 0.95, stop: list[str] | None = None, seed: int | None = None, stream: bool = True) -> AsyncIterator[Token]`
- `complete(*, model: str, prompt: str, max_tokens: int = 256, temperature: float = 0.7, top_p: float = 0.95, stop: list[str] | None = None, seed: int | None = None, stream: bool = True) -> AsyncIterator[Token]`
- `count_tokens(model: str, text: str) -> int`
- `max_concurrent(model: str) -> int`
- `health() -> dict`

### Concrete backends — §3.2

Each implements `LlmBackend`. Same method set; only constructor varies.

| File | Class | Constructor signature |
|------|-------|-----------------------|
| `backends/llama_cpp.py` | `LlamaCppBackend` | `__init__(model_path: Path, model_meta: BackendModel, gpu_layers: int = -1)` |
| `backends/ollama.py` | `OllamaBackend` | `__init__(base_url: str = "http://localhost:11434", models: list[str] | None = None)` |
| `backends/lmstudio.py` | `LmStudioBackend` | `__init__(base_url: str, default_model: str)` — OpenAI-compatible HTTP |
| `backends/hf_api.py` | `HfApiBackend` | `__init__(model: str, token_env: str = "HF_TOKEN")` — `requires_internet=True` |
| `backends/anthropic_api.py` | `AnthropicApiBackend` | `__init__(model: str = "claude-sonnet-4-6", token_env: str = "ANTHROPIC_API_KEY")` — `requires_internet=True` |
| `backends/nemotron.py` *(new)* | `NemotronBackend` | `__init__(base_url: str = "https://integrate.api.nvidia.com/v1", model: str = "nvidia/llama-3.1-nemotron-70b-instruct", token_env: str = "NVIDIA_API_KEY", local: bool = False)` — OpenAI-compatible; `requires_internet=True` unless `local=True` (locally-hosted NIM endpoint) |
| `backends/openbmb.py` *(new)* | `OpenBmbBackend` | `__init__(base_url: str = "http://localhost:8000", model: str = "openbmb/MiniCPM4-8B", token_env: str | None = None)` — OpenAI-compatible HTTP (vLLM / llama.cpp serve / SGLang); `requires_internet=False`. Designed around Christof's MiniCPM workbench |

All backends declare their `models: list[BackendModel]` so the service can enumerate `(backend, model)` pairs at registration time.

### `hearthnet/services/llm/tokenizers.py` — §3.3

- `count_tokens_approx(model_family: str, text: str) -> int`
- `model_family(model_name: str) -> str` — e.g. `"qwen2.5-7b-instruct"` → `"qwen"`, `"nemotron-70b"` → `"nemotron"`, `"MiniCPM4-8B"` → `"minicpm"`.

### `hearthnet/services/llm/service.py` — §3.4

`LlmService` *(implements `Service`)*:
- `name = "llm"`, `version = "1.0"`
- `__init__(config: LlmConfig)`
- `_build_backends(config: LlmConfig) -> list[LlmBackend]`
- `capabilities() -> [...]` — emits one descriptor per `(backend, model)` × `{llm.chat, llm.complete}`.
- `start(), stop(), health()` *(async)*
- `handle_chat(req: RouteRequest) -> AsyncIterator[dict]` *(async)* — implements [CONTRACT §4.1](CAPABILITY_CONTRACT.md).
- `handle_complete(req: RouteRequest) -> AsyncIterator[dict]` *(async)* — implements [CONTRACT §4.2](CAPABILITY_CONTRACT.md).

#### Capability params predicate — §3.6

```python
def params_compatible(offered: dict, requested: dict) -> bool:
    if requested.get("model") != offered.get("model"):
        return False
    if "ctx" in requested and requested["ctx"] > offered["ctx"]:
        return False
    return True
```

---

## 10. M05 — RAG Service

**Spec:** [`modules/M05-rag.md`](modules/M05-rag.md) · **Path:** `hearthnet/services/rag/`

### `hearthnet/services/rag/chunker.py` — §3.1

`Chunk` *(frozen dataclass)*: `text: str`, `metadata: dict`.

Functions:
- `chunk_text(text: str, *, tokens_per_chunk: int = RAG_CHUNK_TOKENS, overlap_tokens: int = RAG_CHUNK_OVERLAP_TOKENS, metadata: dict | None = None) -> list[Chunk]`
- `chunk_pdf(pdf_bytes: bytes, *, doc_metadata: dict) -> list[Chunk]`

### `hearthnet/services/rag/store.py` — §3.2

`ScoredChunk` *(frozen dataclass)*: `chunk: Chunk`, `score: float`.

`CorpusStore`:
- `__init__(corpora_dir: Path, corpus: str, embedding_dim: int)`
- `add_chunks(chunks: list[Chunk], embeddings: list[list[float]]) -> None`
- `has_document(doc_cid: str) -> bool`
- `query(embedding: list[float], *, k: int, filter: dict | None = None) -> list[ScoredChunk]`
- `count() -> int`
- `size_bytes() -> int`
- `language_majority() -> str | None`

Free functions:
- `list_corpora(corpora_dir: Path) -> list[str]`
- `corpus_info(corpora_dir: Path, corpus: str) -> dict`

### `hearthnet/services/rag/ingest.py` — §3.3

`IngestResult` *(frozen dataclass)*: `doc_cid: str`, `chunks_indexed: int`, `tokens_indexed: int`, `ingest_event_id: str`, `ms: int`.

`IngestPipeline`:
- `__init__(bus: CapabilityBus, blob_store: BlobStore, corpora_dir: Path, event_log: EventLog)`
- `ingest_document(doc_cid: str, corpus: str, title: str, language: str, metadata: dict, author_kp: KeyPair) -> IngestResult` *(async)*

### `hearthnet/services/rag/service.py` — §3.4

`RagService` *(implements `Service`)*:
- `name = "rag"`, `version = "1.0"`
- `__init__(config: RagConfig, bus: CapabilityBus, blob_store: BlobStore, event_log: EventLog, community_manifest_provider: Callable[[], CommunityManifest])`
- `capabilities() -> [...]` — `rag.query@1.0` per corpus, `rag.ingest@1.0` once, `rag.list_corpora@1.0` once.
- `start(), stop(), health()` *(async)*
- `handle_query(req: RouteRequest) -> dict` *(async)* — [CONTRACT §4.4](CAPABILITY_CONTRACT.md).
- `handle_ingest(req: RouteRequest) -> dict` *(async)* — [CONTRACT §4.5](CAPABILITY_CONTRACT.md).
- `handle_list_corpora(req: RouteRequest) -> dict` *(async)* — [CONTRACT §4.6](CAPABILITY_CONTRACT.md).

#### Capability params predicate — §3.5

```python
def query_params_compatible(offered: dict, requested: dict) -> bool:
    return requested.get("corpus") == offered.get("corpus")
```

---

## 11. M07 — File & Blobs

**Spec:** [`modules/M07-file-blobs.md`](modules/M07-file-blobs.md) · **Paths:** `hearthnet/blobs/` + `hearthnet/services/file/`

### `hearthnet/blobs/chunker.py` — §3.1

`ChunkRef` *(frozen)*: `index: int`, `cid: str`, `size_bytes: int`.

`BlobManifest` *(frozen)*: `cid: str`, `size_bytes: int`, `chunk_size_bytes: int`, `chunks: list[ChunkRef]`, `mime_type: str | None`, `filename: str | None`.

Functions:
- `hash_bytes(data: bytes) -> str` — `"blake3:<hex>"`.
- `chunk_blob(data: bytes, *, chunk_size: int = CHUNK_SIZE_BYTES) -> tuple[BlobManifest, list[bytes]]`
- `manifest_cid(manifest: BlobManifest) -> str`
- `reassemble(chunks: list[bytes]) -> bytes`
- `verify_chunk(data: bytes, expected_cid: str) -> None` — raises `BlobError("hash_mismatch")`.

### `hearthnet/blobs/store.py` — §3.2

`BlobStore`:
- `__init__(dir_path: Path, gc_threshold: float = BLOB_GC_DISK_THRESHOLD)`
- `has(cid: str) -> bool`
- `read_chunk(cid: str) -> bytes`
- `write_chunk(cid: str, data: bytes) -> None`
- `delete_chunk(cid: str) -> bool`
- `has_blob(manifest_cid: str) -> bool`
- `read_manifest(manifest_cid: str) -> BlobManifest`
- `write_blob(manifest: BlobManifest, chunks: list[bytes]) -> None`
- `read_blob_bytes(manifest_cid: str) -> bytes`
- `read_blob_stream(manifest_cid: str) -> AsyncIterator[tuple[ChunkRef, bytes]]` *(async)*
- `list_cids(prefix: str | None = None) -> list[str]`
- `total_bytes() -> int`
- `pin(cid: str) -> None`
- `unpin(cid: str) -> None`
- `is_pinned(cid: str) -> bool`
- `gc(target_fraction: float = 0.7) -> int` — bytes freed.

`BlobError(Exception)`:
- `code in {"not_found","hash_mismatch","io_error","disk_full","manifest_invalid"}`

### `hearthnet/blobs/transfer.py` — §3.3

`TransferManager`:
- `__init__(store: BlobStore, bus: CapabilityBus, concurrency: int = 4)`
- `fetch_blob(manifest_cid: str, *, sources: list[str] | None = None) -> BlobManifest` *(async)*
- `advertise(cids: list[str]) -> None` *(async)*

### `hearthnet/services/file/service.py` — §4.1

`FileService` *(implements `Service`)*:
- `name = "file"`, `version = "1.0"`
- `__init__(config: FileConfig, store: BlobStore, event_log: EventLog)`
- `capabilities() -> [...]` — `file.read`, `file.list`, `file.advertise`, `file.put` (all `@1.0`).
- `start(), stop(), health()` *(async)*
- `handle_read(req: RouteRequest) -> AsyncIterator[dict] | dict` *(async)* — [CONTRACT §4.7](CAPABILITY_CONTRACT.md).
- `handle_list(req: RouteRequest) -> dict` *(async)* — [CONTRACT §4.8](CAPABILITY_CONTRACT.md).
- `handle_advertise(req: RouteRequest) -> dict` *(async)* — [CONTRACT §4.9](CAPABILITY_CONTRACT.md).
- `handle_put(req: RouteRequest) -> AsyncIterator[dict]` *(async)* — [CONTRACT §4.10](CAPABILITY_CONTRACT.md).

All four `file.*` use default `lambda offered, requested: True` as params predicate.

---

## 12. M06 — Marketplace Service

**Spec:** [`modules/M06-marketplace.md`](modules/M06-marketplace.md) · **Path:** `hearthnet/services/marketplace/`

### `hearthnet/services/marketplace/post.py` — §3.1

`Location` *(frozen dataclass)*: `lat: float`, `lng: float`, `label: str`.

`Post` *(frozen dataclass)*:
- `event_id: str`, `lamport: int`, `author: str`, `category: Category`, `title: str`, `body: str`, `location: Location | None`, `tags: list[str]`, `created_at: str`, `expires_at: str`, `expired_via_event_id: str | None`, `expiry_reason: str | None`.
- `is_expired(now: datetime | None = None) -> bool`

### `hearthnet/services/marketplace/views.py` — §3.2

`MarketplaceView` *(implements `MaterialisedView` from X02)*:
- `__init__()`
- `reset() -> None`
- `apply(event: Event) -> None`
- `snapshot_state() -> dict`
- `restore_state(state: dict) -> None`
- `list(*, category: Category | None = None, tags: list[str] | None = None, since_lamport: int = 0, limit: int = 50) -> list[Post]`
- `get(event_id: str) -> Post | None`
- `max_lamport() -> int`
- `all_active() -> list[Post]`

### `hearthnet/services/marketplace/service.py` — §3.3

`MarketplaceService` *(implements `Service`)*:
- `name = "marketplace"`, `version = "1.0"`
- `__init__(config: MarketConfig, bus: CapabilityBus, event_log: EventLog, replay_engine: ReplayEngine, author_kp: KeyPair, community_manifest_provider: Callable[[], CommunityManifest])`
- `capabilities() -> [...]` — `market.list`, `market.post`, `market.expire`, `market.search` (all `@1.0`).
- `start(), stop(), health()` *(async)* — start replays events and installs auto-expiry sweeper.
- `handle_list(req) -> dict` *(async)* — [CONTRACT §4.11](CAPABILITY_CONTRACT.md).
- `handle_post(req) -> dict` *(async)* — [CONTRACT §4.12](CAPABILITY_CONTRACT.md).
- `handle_expire(req) -> dict` *(async)* — [CONTRACT §4.13](CAPABILITY_CONTRACT.md).
- `handle_search(req) -> dict` *(async)* — [CONTRACT §4.14](CAPABILITY_CONTRACT.md).
- `_auto_expire_sweep() -> None` *(async)* — internal background task.

All four use default `lambda offered, requested: True` predicate.

---

## 13. M10 — Chat Service

**Spec:** [`modules/M10-chat.md`](modules/M10-chat.md) · **Path:** `hearthnet/services/chat/`

### `hearthnet/services/chat/views.py` — §3.1

`ChatMessage` *(frozen dataclass)*:
- `event_id: str`, `lamport: int`, `sender: str`, `recipient: str`, `body: str`, `attachments: list[dict]`, `created_at: str`, `delivered_at: str | None`, `read_at: str | None`.

`ChatView` *(implements `MaterialisedView`)*:
- `__init__(our_node_id_full: str)`
- `reset(), apply(event), snapshot_state(), restore_state(state)`
- `history_with(peer: str | None = None, *, since_lamport: int = 0, limit: int = 200) -> list[ChatMessage]`
- `peers() -> list[str]`
- `unread_count(peer: str) -> int`

### `hearthnet/services/chat/delivery.py` — §3.2

`DeliveryManager`:
- `__init__(bus: CapabilityBus, event_log: EventLog, author_kp: KeyPair, peer_registry: PeerRegistry, config: ChatConfig)`
- `deliver(message_event: Event) -> str` *(async)* — returns `"direct"|"forwarded"|"queued"`.
- `on_local_message_arrived(message_event: Event) -> None` *(async)*
- `on_pubsub_message(payload: dict) -> None` *(async)*

### `hearthnet/services/chat/service.py` — §3.3

`ChatService` *(implements `Service`)*:
- `name = "chat"`, `version = "1.0"`
- `__init__(config: ChatConfig, bus: CapabilityBus, event_log: EventLog, replay_engine: ReplayEngine, peer_registry: PeerRegistry, author_kp: KeyPair, our_node_id_full: str)`
- `capabilities() -> [...]` — `chat.send@1.0` (member trust), `chat.history@1.0` (self trust).
- `start(), stop(), health()` *(async)*
- `handle_send(req) -> dict` *(async)* — [CONTRACT §4.15](CAPABILITY_CONTRACT.md).
- `handle_history(req) -> dict` *(async)* — [CONTRACT §4.16](CAPABILITY_CONTRACT.md). Enforces `caller == our_node_id_full`.

---

## 14. M09 — Emergency Mode Detector

**Spec:** [`modules/M09-emergency.md`](modules/M09-emergency.md) · **Path:** `hearthnet/emergency/`

### `hearthnet/emergency/state.py` — §3.1

`EmergencyState` *(frozen dataclass)*:
- `mode: Mode`, `since: WallClock`, `last_probe: WallClock`, `probe_results: dict[str, bool]`.

`StateBus`:
- `__init__()`
- `current() -> EmergencyState`
- `subscribe() -> AsyncIterator[EmergencyState]`
- `_emit(state: EmergencyState) -> None` *(internal)*

### `hearthnet/emergency/detector.py` — §3.2

`Detector`:
- `__init__(config: EmergencyConfig, bus: CapabilityBus, state_bus: StateBus)`
- `run() -> None` *(async)*
- `shutdown() -> None` *(async)*
- `_probe_dns(host: str) -> bool` *(async, internal)*
- `_probe_http(url: str) -> bool` *(async, internal)*

State-transition effects (§5.2):
- entering offline → deregister local capabilities whose descriptor `params.requires_internet == True`
- entering online → re-register those backends
- offline ↔ online → flip `peer_registry.set_pruning_aggressive(...)` (M02)

---

## 15. M08 — UI

**Spec:** [`modules/M08-ui.md`](modules/M08-ui.md) · **Path:** `hearthnet/ui/`

### `hearthnet/ui/app.py` — §3.1

`UiApp`:
- `__init__(bus: CapabilityBus, state_bus: StateBus, config: UiConfig, node_id_short: str, community_name: str)`
- `build() -> gr.Blocks`
- `launch_async() -> None` *(async)*
- `shutdown() -> None` *(async)*

Free function:
- `build_ui(bus: CapabilityBus, state_bus: StateBus, config: UiConfig, **meta) -> UiApp`

### `hearthnet/ui/topology.py` — §3.2

`TopologyComponent`:
- `__init__(bus: CapabilityBus)`
- `render() -> gr.HTML`
- `push_trace(event: CallTraceEvent) -> None`
- `push_topology(snapshot: TopologySnapshot) -> None`

### `hearthnet/ui/theme.py` — §7

- `hearthnet_theme: gr.Theme` *(module-level constant)*
- `emergency_theme: gr.Theme` *(module-level constant)*
- CSS variables documented in spec §7

### `hearthnet/ui/tabs/`

Each file exports a builder function returning a `gr.Tab` or `gr.Blocks` fragment.

| File | Function | Spec |
|------|----------|------|
| `tabs/ask.py` | `build_ask_tab(bus: CapabilityBus) -> gr.Tab` | §5.1 |
| `tabs/chat.py` | `build_chat_tab(bus: CapabilityBus, our_node_id_full: str) -> gr.Tab` | §5.3 |
| `tabs/marketplace.py` | `build_marketplace_tab(bus: CapabilityBus) -> gr.Tab` | §5.4 |
| `tabs/files.py` | `build_files_tab(bus: CapabilityBus) -> gr.Tab` | §5.5 |
| `tabs/emergency.py` | `build_emergency_tab(bus: CapabilityBus, state_bus: StateBus) -> gr.Tab` | §5.6 |
| `tabs/settings.py` | `build_settings_tab(bus: CapabilityBus, config: Config) -> gr.Tab` | §5.2 |

### `hearthnet/ui/mobile/` — §6

Static assets served at `/mobile/*` by [X01](cross-cutting/X01-transport.md):
- `index.html` — single-page app
- `app.js` — same bus API; uses signed requests via WebCrypto
- `style.css`

---

## 16. M13 — Onboarding

**Spec:** [`modules/M13-onboarding.md`](modules/M13-onboarding.md) · **Path:** `hearthnet/ui/onboarding.py`

### `hearthnet/ui/onboarding.py` — §3.1

`InviteBlob` *(frozen dataclass)*:
- `schema_version: int`, `community_id: str`, `community_name: str`, `inviter_node_id: str`, `invitee_node_id: str`, `initial_level: str`, `bootstrap_endpoints: list[Endpoint]`, `expires_at: str`, `signature: str`.

#### Functions

- `encode_invite(blob: InviteBlob) -> str` — `"hearthnet://v1/<base64>"`.
- `decode_invite(text: str) -> InviteBlob`
- `invite_to_qr_png(blob: InviteBlob, *, box_size: int = 8) -> bytes`
- `create_community(name: str, policy: CommunityPolicy, kp: KeyPair, state_dir: Path, event_log: EventLog) -> CommunityManifest`
- `make_invite(invitee_node_id_full: str, inviter_kp: KeyPair, community_manifest: CommunityManifest, bootstrap_endpoints: list[Endpoint], initial_level: str = "member", ttl_seconds: int = 86400) -> InviteBlob`
- `redeem_invite(blob: InviteBlob, our_kp: KeyPair, transport_client: HttpClient, event_log: EventLog) -> CommunityManifest` *(async)*
- `build_onboarding(config: Config, kp_provider: Callable[[], KeyPair]) -> gr.Blocks`

Exception:
`OnboardingError(Exception)`:
- `code in {"invite_invalid","invite_expired","invitee_mismatch","bootstrap_unreachable","community_manifest_invalid","sync_failed","already_member"}`

---

## 17. M12 — CLI & Orchestrator

**Spec:** [`modules/M12-cli.md`](modules/M12-cli.md) · **Paths:** `hearthnet/cli.py` + `hearthnet/node.py`

### `hearthnet/cli.py` — §3

Click group + subcommands. Each is a top-level function decorated with `@main.command()`.

| Command | Function | Spec |
|---------|----------|------|
| (root) | `main(ctx, config)` | §4 |
| `init` | `init(name: str, profile: str, non_interactive: bool)` | §3.1 |
| `run` | `run(config: str, no_ui: bool, debug: bool)` | §3.2 |
| `status` | `status(json_output: bool)` | §3.3 |
| `caps` | `caps(remote_only: bool, local_only: bool, name: str)` | §3.4 |
| `call` | `call(name_at_version: str, body: str, stream: bool)` | §3.5 |
| `log` | `log(follow: bool, level: str, component: str)` | §3.6 |
| `trace` | `trace_recent(n: int, capability: str)` | §3.7 |
| `doctor` | `doctor(check: str)` | §3.8 |
| `export` | `export(out: str)` | §3.9 |
| `erase` | `erase(keep_keys: bool, yes: bool)` | §3.10 |
| `rag list` | `rag_list()` | §3.11 |
| `rag ingest` | `rag_ingest(path: str, corpus: str)` | §3.11 |
| `rag reindex` | `rag_reindex(corpus: str, embedding_model: str)` | §3.11 |
| `invite create` | `invite_create(node_id: str, level: str, ttl: int)` | §3.12 |
| `invite redeem` | `invite_redeem(text_or_path: str)` | §3.12 |
| `version` | `version_cmd()` | §3.13 |

Exit codes — §6: `0` success, `1` generic error, `2` user abort / bad usage, `3` no running node, `4` auth, `5` capacity.

### `hearthnet/node.py` — §5

Single function — the canonical wiring:

```python
async def start(config: Config) -> None:
    """The 15-step composition. Do not deviate."""
```

Sequence (each numbered in spec §5):
1. observability configure
2. identity load_or_generate
3. community check / onboarding redirect
4. event log + snapshot store + replay engine + community manifest
5. blob store
6. pinned-certs + transport client + bus
7. peer registry + mdns/udp announcer + listener
8. instantiate services (Embedding, Llm, Rag, File, Marketplace, Chat) and register with bus
9. state bus + Detector
10. http server
11. UI app
12. wire peer events → bus
13. ManifestPublisher
14. SyncClient periodic loop
15. asyncio.gather(...) — block until shutdown

Auxiliary class declared inline in this module:

`ManifestPublisher`:
- `__init__(kp: KeyPair, community_manifest_provider: Callable, bus: CapabilityBus, peer_registry: PeerRegistry, interval_seconds: int = MANIFEST_REPUBLISH_INTERVAL_SECONDS)`
- `run() -> None` *(async)*
- Publishes the freshly-built node manifest to mDNS + UDP every `interval_seconds`. Triggered also on `bus.registry` change events (capability added/removed).

`PeriodicTask` *(helper)*:
- `__init__(fn: Callable[[], Awaitable], interval_seconds: int)`
- `run() -> None` *(async)*

### `hearthnet/__main__.py`

Single line: `from hearthnet.cli import main; main()`

---

## 18. Cross-module symbol index (alphabetical)

For "where is `X` declared?"

| Symbol | Module | File |
|--------|--------|------|
| `AnthropicApiBackend` | M04 | `services/llm/backends/anthropic_api.py` |
| `BackendModel` | M04 | `services/llm/backends/base.py` |
| `BlobError` | M07 | `blobs/store.py` |
| `BlobManifest` | M07 | `blobs/chunker.py` |
| `BlobStore` | M07 | `blobs/store.py` |
| `BusConfig` | X04 | `config.py` |
| `BusError` | M03 | `bus/__init__.py` |
| `CallError` | X01 | `transport/client.py` |
| `CallTraceEvent` | M03 | `bus/trace.py` |
| `CapabilityBus` | M03 | `bus/__init__.py` |
| `CapabilityDescriptor` | M03 | `bus/capability.py` |
| `CapabilityEntry` | M03 | `bus/capability.py` |
| `CapabilitySpec` | M01 | `identity/manifest.py` |
| `CapabilityToken` | M01 | `identity/tokens.py` |
| `Category` | M06 | `services/marketplace/post.py` (Literal alias) |
| `ChatConfig` | X04 | `config.py` |
| `ChatMessage` | M10 | `services/chat/views.py` |
| `ChatService` | M10 | `services/chat/service.py` |
| `ChatView` | M10 | `services/chat/views.py` |
| `CheckResult` | X03 | `observability/doctor.py` |
| `Chunk` | M05 | `services/rag/chunker.py` |
| `ChunkRef` | M07 | `blobs/chunker.py` |
| `CommunityConfig` | X04 | `config.py` |
| `CommunityManifest` | M01 | `identity/manifest.py` |
| `CommunityMember` | M01 | `identity/manifest.py` |
| `CommunityPolicy` | M01 | `identity/manifest.py` |
| `Config` | X04 | `config.py` |
| `ConfigError` | X04 | `config.py` |
| `CorpusStore` | M05 | `services/rag/store.py` |
| `DeliveryManager` | M10 | `services/chat/delivery.py` |
| `Detector` | M09 | `emergency/detector.py` |
| `Diff` | M03 | `bus/registry.py` |
| `DiscoveryConfig` | X04 | `config.py` |
| `DiscoveryError` | M02 | `discovery/__init__.py` |
| `EmbeddingBackend` | M11 | `services/embedding/backends.py` |
| `EmbeddingConfig` | X04 | `config.py` |
| `EmbeddingService` | M11 | `services/embedding/service.py` |
| `EmergencyConfig` | X04 | `config.py` |
| `EmergencyState` | M09 | `emergency/state.py` |
| `Endpoint` | M01 | `identity/manifest.py` |
| `Event` | X02 | `events/types.py` |
| `EventLog` | X02 | `events/log.py` |
| `EventLogError` | X02 | `events/log.py` |
| `EventType` | X02 | `events/types.py` |
| `FileConfig` | X04 | `config.py` |
| `FileService` | M07 | `services/file/service.py` |
| `FlowControl` | X01 | `transport/backpressure.py` |
| `Frame` | X01 | `transport/streams.py` |
| `HardwareSpec` | M01 | `identity/manifest.py` |
| `HeadsReport` | X02 | `events/sync.py` |
| `HealthTracker` | M03 | `bus/health.py` |
| `HfApiBackend` | M04 | `services/llm/backends/hf_api.py` |
| `HttpClient` | X01 | `transport/client.py` |
| `HttpServer` | X01 | `transport/server.py` |
| `IdentityConfig` | X04 | `config.py` |
| `IdentityError` | M01 | `identity/keys.py` |
| `IngestPipeline` | M05 | `services/rag/ingest.py` |
| `IngestResult` | M05 | `services/rag/ingest.py` |
| `InviteBlob` | M13 | `ui/onboarding.py` |
| `JsonFormatter` | X03 | `observability/logging.py` |
| `KeyPair` | M01 | `identity/keys.py` |
| `LamportClock` | X02 | `events/lamport.py` |
| `LlamaCppBackend` | M04 | `services/llm/backends/llama_cpp.py` |
| `LlmBackend` | M04 | `services/llm/backends/base.py` |
| `LlmBackendConfig` | X04 | `config.py` |
| `LlmConfig` | X04 | `config.py` |
| `LlmService` | M04 | `services/llm/service.py` |
| `LmStudioBackend` | M04 | `services/llm/backends/lmstudio.py` |
| `Location` | M06 | `services/marketplace/post.py` |
| `ManifestPublisher` | M12 | `node.py` |
| `MarketConfig` | X04 | `config.py` |
| `MarketplaceService` | M06 | `services/marketplace/service.py` |
| `MarketplaceView` | M06 | `services/marketplace/views.py` |
| `MaterialisedView` | X02 | `events/replay.py` (Protocol) |
| `MdnsAnnouncer` | M02 | `discovery/mdns.py` |
| `MdnsBrowser` | M02 | `discovery/mdns.py` |
| `Mode` | M09 | `emergency/state.py` (Literal alias) |
| `NemotronBackend` *(new)* | M04 | `services/llm/backends/nemotron.py` |
| `NodeManifest` | M01 | `identity/manifest.py` |
| `ObservabilityConfig` | X04 | `config.py` |
| `OllamaBackend` | M04 | `services/llm/backends/ollama.py` |
| `OnboardingError` | M13 | `ui/onboarding.py` |
| `OpenBmbBackend` *(new)* | M04 | `services/llm/backends/openbmb.py` |
| `ParamsPredicate` | M03 | `bus/capability.py` (type alias) |
| `PeerEvent` | M02 | `discovery/peers.py` |
| `PeerRecord` | M02 | `discovery/peers.py` |
| `PeerRegistry` | M02 | `discovery/peers.py` |
| `PeriodicTask` | M12 | `node.py` |
| `PinnedCerts` | X01 | `transport/tls.py` |
| `Post` | M06 | `services/marketplace/post.py` |
| `Profile` | (types) | `hearthnet/types.py` (Literal alias) |
| `PubSubServer` | X01 | `transport/server.py` |
| `RagConfig` | X04 | `config.py` |
| `RagService` | M05 | `services/rag/service.py` |
| `RateCheck` | X01 | `transport/__init__.py` |
| `RateLimiter` | X01 | `transport/__init__.py` |
| `RateLimitedLogger` | X03 | `observability/logging.py` |
| `Registry` | M03 | `bus/registry.py` |
| `RegistryEvent` | M03 | `bus/registry.py` |
| `ReplayEngine` | X02 | `events/replay.py` |
| `RevokedEntry` | M01 | `identity/manifest.py` |
| `RouteRequest` | M03 | `bus/capability.py` |
| `Router` | M03 | `bus/router.py` |
| `SchemaValidator` | M03 | `bus/schema.py` |
| `ScoredChunk` | M05 | `services/rag/store.py` |
| `SentenceTransformerBackend` | M11 | `services/embedding/backends.py` |
| `Service` | M03 | `services/base.py` (Protocol) |
| `Snapshot` | X02 | `events/snapshot.py` |
| `SnapshotStore` | X02 | `events/snapshot.py` |
| `Span` | X03 | `observability/tracing.py` |
| `SseReader` | X01 | `transport/streams.py` |
| `SseWriter` | X01 | `transport/streams.py` |
| `StateBus` | M09 | `emergency/state.py` |
| `SyncClient` | X02 | `events/sync.py` |
| `SyncResult` | X02 | `events/sync.py` |
| `SyncServer` | X02 | `events/sync.py` |
| `Token` | M04 | `services/llm/backends/base.py` |
| `TopologyComponent` | M08 | `ui/topology.py` |
| `TopologySnapshot` | M03 | `bus/__init__.py` |
| `Trace` | X03 | `observability/tracing.py` |
| `TraceHook` | M03 | `bus/trace.py` |
| `TrackioExporter` *(new)* | X03 | `observability/metrics.py` |
| `TransferManager` | M07 | `blobs/transfer.py` |
| `TransportConfig` | X04 | `config.py` |
| `UdpAnnouncer` | M02 | `discovery/udp.py` |
| `UdpListener` | M02 | `discovery/udp.py` |
| `UiApp` | M08 | `ui/app.py` |
| `UiConfig` | X04 | `config.py` |

---

## 19. Capability → handler index

For each capability in [CONTRACT §3.2](CAPABILITY_CONTRACT.md), where the handler lives:

| Capability | Service | Handler | Trust |
|------------|---------|---------|-------|
| `llm.chat@1.0` | M04 `LlmService` | `handle_chat` | member |
| `llm.complete@1.0` | M04 `LlmService` | `handle_complete` | member |
| `embed.text@1.0` | M11 `EmbeddingService` | `handle_embed_text` | member |
| `rag.query@1.0` | M05 `RagService` | `handle_query` | member |
| `rag.ingest@1.0` | M05 `RagService` | `handle_ingest` | trusted |
| `rag.list_corpora@1.0` | M05 `RagService` | `handle_list_corpora` | member |
| `file.read@1.0` | M07 `FileService` | `handle_read` | member |
| `file.list@1.0` | M07 `FileService` | `handle_list` | member |
| `file.advertise@1.0` | M07 `FileService` | `handle_advertise` | member |
| `file.put@1.0` | M07 `FileService` | `handle_put` | trusted |
| `market.list@1.0` | M06 `MarketplaceService` | `handle_list` | member |
| `market.post@1.0` | M06 `MarketplaceService` | `handle_post` | member |
| `market.expire@1.0` | M06 `MarketplaceService` | `handle_expire` | member |
| `market.search@1.0` | M06 `MarketplaceService` | `handle_search` | member |
| `chat.send@1.0` | M10 `ChatService` | `handle_send` | member |
| `chat.history@1.0` | M10 `ChatService` | `handle_history` | self |
| `community.invite@1.0` | M13 (handler via bus from `make_invite`) | n/a | member with `can_invite` |
| `community.revoke@1.0` | M13 / M01 helper | n/a | 3 trusted signatures |

---

## 20. Event-type → producer/consumer index

For each [CONTRACT §7.2](CAPABILITY_CONTRACT.md) event type:

| Event type | Produced by | View(s) consuming |
|------------|-------------|--------------------|
| `community.created` | M13 `create_community` | M01 community manifest builder |
| `community.member.invited` | M13 `make_invite` | M01 |
| `community.member.joined` | M13 `redeem_invite` | M01 |
| `community.member.revoked` | M01 helper / `community.revoke` handler | M01 |
| `community.member.promoted` / `.demoted` | M01 helpers | M01 |
| `community.policy.updated` | M01 (root key only) | M01 |
| `node.manifest.updated` | M12 `ManifestPublisher` | optional audit views |
| `market.post.created` | M06 `handle_post` | M06 `MarketplaceView` |
| `market.post.updated` | M06 (author only) | M06 `MarketplaceView` |
| `market.post.expired` | M06 (author or sweeper) | M06 `MarketplaceView` |
| `chat.message.sent` | M10 `handle_send` | M10 `ChatView` |
| `chat.message.delivered` | M10 `DeliveryManager` | M10 `ChatView` |
| `chat.message.read` | M10 (UI) | M10 `ChatView` |
| `file.cid.advertised` | M07 `TransferManager.advertise` | local source index in `FileService` |
| `file.cid.unpinned` | M07 `BlobStore.unpin` | local source index |
| `rag.document.ingested` | M05 `IngestPipeline` | M05 (replicas may pre-fetch) |
| `federation.peer.added` / `.removed` | reserved (Phase 2) | — |

---

## 21. Standard params for each capability descriptor

Used by [CONTRACT §6.1](CAPABILITY_CONTRACT.md) node manifest embedding and by the bus's params-compatibility check.

| Capability | `params` keys |
|------------|---------------|
| `llm.chat` | `model`, `quant`, `ctx`, `backend`, `modalities`, optionally `requires_internet` |
| `llm.complete` | same as `llm.chat` |
| `embed.text` | `model` |
| `rag.query` | `corpus`, `embedding_model`, `k_max` |
| `rag.ingest` | `corpora_available` (list) |
| `rag.list_corpora` | `{}` |
| `file.read` | `{}` |
| `file.list` | `{}` |
| `file.advertise` | `{}` |
| `file.put` | `{}` |
| `market.*` | `{}` |
| `chat.send` | `{}` |
| `chat.history` | `{}` |

---

## 22. Implementation checklist (one row per implementable unit)

Tick these off as you build. Order: dependency-correct.

### X04 Config (~6 dataclasses, ~5 functions, ~1 exception)
- [ ] `IdentityConfig`, `CommunityConfig`, `TransportConfig`, `DiscoveryConfig`, `BusConfig`
- [ ] `LlmBackendConfig`, `LlmConfig`
- [ ] `EmbeddingConfig`, `RagConfig`, `FileConfig`, `MarketConfig`, `ChatConfig`
- [ ] `EmergencyConfig`, `UiConfig`, `ObservabilityConfig` *(incl. trackio_project/trackio_space)*
- [ ] `Config` (aggregate)
- [ ] `load`, `default_config`, `save`, `resolve_paths`, `validate`
- [ ] `ConfigError`
- [ ] `constants.py` with all 31 named constants

### X03 Observability (~6 classes, ~14 functions)
- [ ] `configure`, `get_logger`, `JsonFormatter`, `RateLimitedLogger`
- [ ] `configure` (metrics), `counter`, `histogram`, `gauge`, `disabled`
- [ ] All 14 standard metrics pre-registered
- [ ] `TrackioExporter` *(new, optional)*
- [ ] `Trace`, `Span`, `new_trace`, `current_trace`, `attach`, `detach`, `span`, `get_recent`
- [ ] `CheckResult`, `register`, `run_all`, `run_one`
- [ ] 12 standard checks registered

### X02 Events (~7 classes, ~3 functions)
- [ ] `EventType`, `Event`
- [ ] `LamportClock`
- [ ] `EventLog`, `EventLogError`
- [ ] `MaterialisedView` (Protocol), `ReplayEngine`
- [ ] `Snapshot`, `SnapshotStore`, `build_snapshot`, `restore_from_snapshot`
- [ ] `HeadsReport`, `SyncResult`, `SyncClient`, `SyncServer`

### X01 Transport (~9 classes, ~1 exception)
- [ ] `HttpServer` + 10 endpoints
- [ ] `HttpClient`, `CallError`
- [ ] `Frame`, `SseWriter`, `SseReader`
- [ ] `FlowControl`
- [ ] `PinnedCerts`
- [ ] `RateCheck`, `RateLimiter`
- [ ] `PubSubServer`

### M01 Identity (~12 classes, ~16 functions, ~1 exception)
- [ ] `KeyPair`, all keys.py functions, `IdentityError`
- [ ] `Endpoint`, `HardwareSpec`, `CapabilitySpec`, `NodeManifest`
- [ ] `CommunityPolicy`, `CommunityMember`, `RevokedEntry`, `CommunityManifest`
- [ ] All builder/parser/verifier functions
- [ ] `CapabilityToken` stub

### M02 Discovery (~6 classes)
- [ ] `PeerRecord`, `PeerEvent`, `PeerRegistry`
- [ ] `MdnsAnnouncer`, `MdnsBrowser`
- [ ] `UdpAnnouncer`, `UdpListener`
- [ ] `DiscoveryError`

### M03 Capability Bus (~10 classes, ~1 function, ~1 exception) — CRITICAL
- [ ] `CapabilityDescriptor`, `CapabilityEntry`, `RouteRequest`
- [ ] `Diff`, `RegistryEvent`, `Registry`
- [ ] `HealthTracker`
- [ ] `SchemaValidator`, `compute_schema_hash`
- [ ] `Router` (with scoring algorithm from M03 §5.4)
- [ ] `CallTraceEvent`, `TraceHook`
- [ ] `TopologySnapshot`, `CapabilityBus` (facade), `BusError`
- [ ] `Service` Protocol in `services/base.py`

### M11 Embedding (~3 classes)
- [ ] `EmbeddingBackend` Protocol
- [ ] `SentenceTransformerBackend`
- [ ] `EmbeddingService` + `handle_embed_text` + params predicate

### M04 LLM (~6 backends + 3 base classes + 2 base functions + 1 service)
- [ ] `Token`, `ChatResult`, `BackendModel`, `LlmBackend` Protocol
- [ ] `LlamaCppBackend`
- [ ] `OllamaBackend`
- [ ] `LmStudioBackend`
- [ ] `HfApiBackend`
- [ ] `AnthropicApiBackend`
- [ ] **`NemotronBackend`** *(new — NVIDIA NIM / locally-hosted)*
- [ ] **`OpenBmbBackend`** *(new — MiniCPM via vLLM/llama.cpp serve/SGLang)*
- [ ] `count_tokens_approx`, `model_family`
- [ ] `LlmService` + `handle_chat` + `handle_complete` + params predicate

### M05 RAG (~5 classes, ~4 functions)
- [ ] `Chunk`, `chunk_text`, `chunk_pdf`
- [ ] `ScoredChunk`, `CorpusStore`, `list_corpora`, `corpus_info`
- [ ] `IngestResult`, `IngestPipeline`
- [ ] `RagService` + 3 handlers + params predicate

### M07 File & Blobs (~4 classes, ~5 functions, ~1 exception)
- [ ] `ChunkRef`, `BlobManifest`
- [ ] All chunker.py functions
- [ ] `BlobStore`, `BlobError`
- [ ] `TransferManager`
- [ ] `FileService` + 4 handlers

### M06 Marketplace (~3 classes)
- [ ] `Location`, `Post`
- [ ] `MarketplaceView`
- [ ] `MarketplaceService` + 4 handlers + sweeper

### M10 Chat (~3 classes)
- [ ] `ChatMessage`, `ChatView`
- [ ] `DeliveryManager`
- [ ] `ChatService` + 2 handlers

### M09 Emergency (~3 classes)
- [ ] `EmergencyState`, `StateBus`
- [ ] `Detector` (state machine + probe loop)

### M08 UI (~2 classes + ~6 tab builders + theme + mobile assets)
- [ ] `UiApp`, `build_ui`
- [ ] `TopologyComponent`
- [ ] `hearthnet_theme`, `emergency_theme`
- [ ] 6 tab builders
- [ ] Mobile static assets

### M13 Onboarding (~1 class, ~7 functions, ~1 exception)
- [ ] `InviteBlob`
- [ ] All onboarding functions
- [ ] `build_onboarding`
- [ ] `OnboardingError`

### M12 CLI & Orchestrator (~17 commands + ~2 helper classes + 1 function)
- [ ] All 17 Click subcommands
- [ ] `ManifestPublisher`, `PeriodicTask`
- [ ] `node.start()` — the 15-step composition

---

## 23. Notes on the trackio integration

[Trackio](https://github.com/huggingface/trackio) is HuggingFace's local-first experiment tracker built on Gradio. Optional in HearthNet; enable by setting `config.observability.trackio_project`.

Integration points:

1. **Activated by config.** `TrackioExporter` is constructed only if `trackio_project` is set. Otherwise the class is unused; HearthNet runs Prometheus-only.

2. **Bridged from TraceHook.** `M03 §3.6` `TraceHook.on_call_end` checks for an active exporter and forwards. No service code calls trackio directly.

3. **Optional HF Spaces sync.** If `trackio_space` is set, runs mirror to the named Space — handy for sharing demo telemetry. Off by default; the demo on Christof's machine logs locally.

4. **What gets logged.** Each LLM call is one step with: `latency_ms`, `tokens_in`, `tokens_out`, `model`, `backend`, `result`. Topology snapshots logged every 60s with mesh size, online state, capability counts. Marketplace post counts and chat throughput as gauges.

5. **Why this fits HearthNet.** Trackio is local-first (matches HearthNet's ethos), Gradio-native (matches the existing UI stack), and gives Christof a dashboard he already knows how to extend without adding Prometheus + Grafana.

---

## 24. Notes on the Nemotron and OpenBMB backends

Both register exactly like existing backends: as `LlmBackend` implementations producing `BackendModel` entries that the service enumerates as `(backend, model)` capability instances.

### `NemotronBackend`

NVIDIA's Nemotron family (Llama-3.1-Nemotron-70B, Nemotron-mini, Nemotron-4-340B-instruct). Two modes:

- **Cloud (default):** `https://integrate.api.nvidia.com/v1`, OpenAI-compatible. `requires_internet=True`. Free tier exists; bring an `NVIDIA_API_KEY`. M09 will deregister this backend automatically when offline.
- **Local (`local=True`):** point at a self-hosted NIM endpoint or vLLM-served Nemotron model. `requires_internet=False`.

Models declared by `models: list[BackendModel]` at construction time. Use these typical entries:

```python
BackendModel("nvidia/llama-3.1-nemotron-70b-instruct", quant="api", ctx_max=128000, modalities=["text"], requires_internet=True)
BackendModel("nvidia/nemotron-mini-4b-instruct", quant="api", ctx_max=4096, modalities=["text"], requires_internet=True)
```

### `OpenBmbBackend`

OpenBMB's MiniCPM family — Christof's primary local-AI-workbench target. Typically served via vLLM, SGLang, or llama.cpp's HTTP server on `http://localhost:8000` (or wherever the workbench binds). OpenAI-compatible HTTP. `requires_internet=False` (always local).

Models declared:

```python
BackendModel("openbmb/MiniCPM4-8B", quant="fp16", ctx_max=32768, modalities=["text"], requires_internet=False)
BackendModel("openbmb/MiniCPM-V-2_6", quant="fp16", ctx_max=8192, modalities=["text","vision"], requires_internet=False)
```

Vision-capable MiniCPM-V variant is reserved for Phase 2 when [CONTRACT §12 open question 1](CAPABILITY_CONTRACT.md) lifts; vision messages stay text-only in MVP.

### Config example

```toml
[[llm.backends]]
name = "openbmb"
url  = "http://localhost:8000"
model = "openbmb/MiniCPM4-8B"

[[llm.backends]]
name = "nemotron"
url  = "https://integrate.api.nvidia.com/v1"
model = "nvidia/llama-3.1-nemotron-70b-instruct"
api_key_env = "NVIDIA_API_KEY"

[[llm.backends]]
name  = "lmstudio"
url   = "http://192.168.188.25:1234"
model = "qwen2.5-7b-instruct"
```

Three backends, four models if MiniCPM-V is later added → eight capability entries on the bus (two each for `llm.chat` and `llm.complete` × four models). The router picks among them at call time.

---

## 25. Coherence guarantees enforced by this reference

If you implement strictly against this document, the following hold automatically:

- **No symbol name appears in two different modules** — see §18.
- **Every capability has exactly one handler** — see §19.
- **Every event type has at least one producer** — see §20.
- **Every constant is defined in `constants.py` and nowhere else** — see §0.2.
- **The 15-step orchestration produces a runnable node** — see §17 `node.py`.
- **Cross-references resolve** — every `M0N`/`X0N` link points at an existing spec; every spec section number used here exists.

If you find a contradiction between this document and a spec, the spec wins by default — but file the discrepancy. The most common drift will be in field names of capability `params` (caught by the params predicate at registration time).

---

## 26. What is intentionally NOT in this document

- **Test code** — see the `tests/` section in each spec. Implement after the production code compiles.
- **Service-internal helpers** that are pure implementation detail (private functions inside one file with leading underscore). Add as you need them.
- **Phase 2/3 modules** — `federation.*`, `ocr.*`, `tts.*`, `stt.*`, `trans.*`, `img.*`, `chat.thread.*`, `chat.forward.*` are mentioned in specs but have no MVP symbols.
- **Vendor-specific tuning** — llama.cpp `n_threads`, vLLM tensor parallel, Nemotron prompt prefixes. Decide per backend at integration time.

---

*End of HearthNet Implementation Reference.*
*Spec set version: v1.0 · this document touched: 2026-06-09.*