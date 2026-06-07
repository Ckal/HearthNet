# X04 — Configuration

**Spec version:** v1.0
**Depends on:** stdlib only
**Depended on by:** every module

---

## 1. Responsibility

Single source of runtime configuration. Loads from disk, validates, and exposes a typed `Config` object. No module reads environment variables, files, or CLI flags directly — they all read from a `Config` instance handed to them.

---

## 2. File layout

```
hearthnet/
├── config.py        # implementation
└── constants.py     # immutable numeric constants (from GLOSSARY.md §Defaults)
```

`config.toml` lives at `<CONFIG>/config.toml` (see [GLOSSARY.md](../GLOSSARY.md) for path resolution).

---

## 3. The Config object

```python
# hearthnet/config.py
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

@dataclass(frozen=True)
class IdentityConfig:
    """Where keys live, and whether to auto-generate if missing."""
    keys_dir:     Path                        # <DATA>/keys
    auto_generate: bool = True

@dataclass(frozen=True)
class CommunityConfig:
    """Which community this node belongs to, and where its state lives."""
    community_id: Optional[str] = None        # None → must run `hearthnet init`
    state_dir:    Path = Path()               # <DATA>/communities/<id>

@dataclass(frozen=True)
class TransportConfig:
    host: str = "0.0.0.0"
    port: int = 7080
    tls_cert: Optional[Path] = None           # None → self-signed
    tls_key:  Optional[Path] = None

@dataclass(frozen=True)
class DiscoveryConfig:
    mdns_enabled: bool = True
    udp_enabled:  bool = True
    udp_multicast_group: str = "239.255.42.42"
    udp_port: int = 42424
    relay_urls:   list[str] = field(default_factory=list)   # Phase 2

@dataclass(frozen=True)
class BusConfig:
    prefer_local: bool = True
    local_load_threshold: float = 0.80

@dataclass(frozen=True)
class LlmBackendConfig:
    name:  str                                # "llama_cpp" | "ollama" | "lmstudio" | "hf_api" | "anthropic_api"
    url:   Optional[str] = None
    model: Optional[str] = None
    api_key_env: Optional[str] = None         # env var name; the actual key is never stored in config

@dataclass(frozen=True)
class LlmConfig:
    backends: list[LlmBackendConfig] = field(default_factory=list)

@dataclass(frozen=True)
class EmbeddingConfig:
    model: str = "BAAI/bge-small-en-v1.5"
    device: str = "auto"                      # "cpu" | "cuda" | "auto"

@dataclass(frozen=True)
class RagConfig:
    enabled: bool = True
    corpora_dir: Path = Path()                # <CACHE>/embeddings

@dataclass(frozen=True)
class FileConfig:
    blobs_dir: Path = Path()                  # <DATA>/blobs
    gc_threshold: float = 0.80

@dataclass(frozen=True)
class MarketConfig:
    enabled: bool = True
    default_ttl_seconds: int = 86400 * 7      # 7 days
    max_ttl_seconds:     int = 86400 * 30

@dataclass(frozen=True)
class ChatConfig:
    enabled: bool = True
    store_and_forward: bool = True

@dataclass(frozen=True)
class EmergencyConfig:
    probe_targets: list[str] = field(default_factory=lambda: [
        "1.1.1.1", "8.8.8.8", "cloudflare.com", "quad9.net"
    ])

@dataclass(frozen=True)
class UiConfig:
    host: str = "127.0.0.1"
    port: int = 7860
    launch_browser: bool = True

@dataclass(frozen=True)
class ObservabilityConfig:
    log_level: str = "info"
    log_dir:   Path = Path()                  # <LOG>
    metrics_enabled: bool = True
    otlp_endpoint: Optional[str] = None       # Phase 2

@dataclass(frozen=True)
class Config:
    identity:      IdentityConfig
    community:     CommunityConfig
    transport:     TransportConfig
    discovery:     DiscoveryConfig
    bus:           BusConfig
    llm:           LlmConfig
    embedding:     EmbeddingConfig
    rag:           RagConfig
    file:          FileConfig
    market:        MarketConfig
    chat:          ChatConfig
    emergency:     EmergencyConfig
    ui:            UiConfig
    observability: ObservabilityConfig
```

---

## 4. Public API

### `load(path: Path | None = None) -> Config`

Loads from `path` if given, otherwise from the platform-standard location. Applies defaults for omitted sections. Validates and returns a frozen `Config`.

Raises:
- `ConfigError("invalid_toml")` — TOML parse failure
- `ConfigError("invalid_field", field=...)` — type or value validation
- `ConfigError("path_resolution")` — XDG resolution failed (e.g. read-only filesystem)

### `default_config() -> Config`

Returns a Config populated entirely from defaults. Used by tests and `hearthnet init`.

### `save(config: Config, path: Path | None = None) -> None`

Serialises a Config to TOML and writes atomically (write to tempfile, rename). Used by `hearthnet init`.

### `resolve_paths(config: Config) -> Config`

Resolves empty `Path()` fields to their canonical XDG locations. Called by `load()` automatically. Idempotent.

### `validate(config: Config) -> None`

Cross-field validation (e.g. transport port not equal to udp port). Raises `ConfigError` on failure. Called by `load()`.

### `ConfigError(Exception)`

```python
class ConfigError(Exception):
    def __init__(self, code: str, **details):
        self.code = code
        self.details = details
        super().__init__(f"{code}: {details}")
```

---

## 5. Default config.toml

```toml
[identity]
auto_generate = true

[community]
# community_id is set by `hearthnet init`

[transport]
host = "0.0.0.0"
port = 7080

[discovery]
mdns_enabled = true
udp_enabled  = true

[bus]
prefer_local = true
local_load_threshold = 0.8

[[llm.backends]]
name  = "lmstudio"
url   = "http://192.168.188.25:1234"
model = "qwen2.5-7b-instruct"

[embedding]
model  = "BAAI/bge-small-en-v1.5"
device = "auto"

[rag]
enabled = true

[file]
gc_threshold = 0.8

[market]
enabled = true
default_ttl_seconds = 604800
max_ttl_seconds = 2592000

[chat]
enabled = true
store_and_forward = true

[ui]
host = "127.0.0.1"
port = 7860
launch_browser = true

[observability]
log_level = "info"
metrics_enabled = true
```

---

## 6. Cross-cutting constants

`hearthnet/constants.py` holds the values from [GLOSSARY.md §Defaults](../GLOSSARY.md). These are NOT configurable. Examples:

```python
MANIFEST_TTL_SECONDS                   = 30
MANIFEST_REPUBLISH_INTERVAL_SECONDS    = 20
EMERGENCY_PROBE_INTERVAL_ONLINE        = 10
EMERGENCY_PROBE_INTERVAL_OFFLINE       = 2
STREAM_WINDOW_FRAMES                   = 16
CHUNK_SIZE_BYTES                       = 262144
HEALTH_WINDOW_CALLS                    = 100
HEALTH_QUARANTINE_THRESHOLD            = 0.5
HEALTH_QUARANTINE_SECONDS              = 60
# ... see GLOSSARY.md for the complete list
```

Rationale for non-configurability: these affect interop. A node tweaking `MANIFEST_TTL_SECONDS` will desync from the network.

---

## 7. Tests

- `test_default_config_round_trips` — `save(default_config()); load()` returns equal config
- `test_invalid_toml_raises` — malformed TOML → `ConfigError("invalid_toml")`
- `test_missing_required_field_raises` — community section without `community_id` is OK (post-init); but other validations apply
- `test_path_resolution_xdg` — empty paths resolve to user_data_dir, etc.
- `test_env_var_substitution` — `${ENV_VAR}` in TOML strings is expanded by `load()`

---

## 8. References

- Constants list: [GLOSSARY.md](../GLOSSARY.md) §Defaults
- Used by all modules; this is the universal entry point
