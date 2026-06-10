"""HearthNet — X04 Configuration.

Typed, frozen config loaded from TOML. No module reads env-vars or files
directly — they all use a Config instance handed to them.
"""
from __future__ import annotations

import os
import tomllib  # stdlib ≥ 3.11; fallback below
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from hearthnet.constants import (
    CHUNK_SIZE_BYTES,
    EMBED_DEFAULT_MODEL,
    HTTP_PORT,
    MARKET_DEFAULT_TTL_SECONDS,
    MARKET_MAX_TTL_SECONDS,
    UI_PORT,
)

# ── Fall back to tomli for Python < 3.11 ────────────────────────────────────
try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ImportError:
        tomllib = None  # type: ignore[assignment]


# ── Sub-config dataclasses ───────────────────────────────────────────────────

@dataclass(frozen=True)
class IdentityConfig:
    keys_dir: Path = field(default_factory=lambda: Path())
    auto_generate: bool = True


@dataclass(frozen=True)
class CommunityConfig:
    community_id: str | None = None
    state_dir: Path = field(default_factory=lambda: Path())


@dataclass(frozen=True)
class TransportConfig:
    host: str = "0.0.0.0"
    port: int = HTTP_PORT
    tls_cert: Path | None = None
    tls_key: Path | None = None


@dataclass(frozen=True)
class DiscoveryConfig:
    mdns_enabled: bool = True
    udp_enabled: bool = True
    udp_port: int = 7079
    relay_urls: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class BusConfig:
    prefer_local: bool = True
    local_load_threshold: float = 0.80


@dataclass(frozen=True)
class LlmBackendConfig:
    name: str
    model: str = ""
    base_url: str = ""
    api_key_env: str | None = None
    extra: dict = field(default_factory=dict)


@dataclass(frozen=True)
class LlmConfig:
    backends: tuple[LlmBackendConfig, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class EmbeddingConfig:
    model: str = EMBED_DEFAULT_MODEL
    device: str = "auto"


@dataclass(frozen=True)
class RagConfig:
    enabled: bool = True
    corpora_dir: Path = field(default_factory=lambda: Path())


@dataclass(frozen=True)
class FileConfig:
    blobs_dir: Path = field(default_factory=lambda: Path())
    chunk_size_bytes: int = CHUNK_SIZE_BYTES
    gc_threshold: float = 0.80


@dataclass(frozen=True)
class MarketConfig:
    enabled: bool = True
    default_ttl_seconds: int = MARKET_DEFAULT_TTL_SECONDS
    max_ttl_seconds: int = MARKET_MAX_TTL_SECONDS


@dataclass(frozen=True)
class ChatConfig:
    enabled: bool = True
    store_and_forward: bool = True
    read_receipts_enabled: bool = True


@dataclass(frozen=True)
class EmergencyConfig:
    probe_targets: tuple[str, ...] = field(
        default_factory=lambda: (
            "1.1.1.1",
            "8.8.8.8",
            "https://cloudflare.com",
            "https://quad9.net",
        )
    )


@dataclass(frozen=True)
class UiConfig:
    host: str = "127.0.0.1"
    port: int = UI_PORT
    launch_browser: bool = True


@dataclass(frozen=True)
class ObservabilityConfig:
    log_level: str = "info"
    log_dir: Path | None = None
    metrics_enabled: bool = True
    otlp_endpoint: str | None = None


@dataclass(frozen=True)
class Config:
    identity: IdentityConfig = field(default_factory=IdentityConfig)
    community: CommunityConfig = field(default_factory=CommunityConfig)
    transport: TransportConfig = field(default_factory=TransportConfig)
    discovery: DiscoveryConfig = field(default_factory=DiscoveryConfig)
    bus: BusConfig = field(default_factory=BusConfig)
    llm: LlmConfig = field(default_factory=LlmConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    rag: RagConfig = field(default_factory=RagConfig)
    file: FileConfig = field(default_factory=FileConfig)
    market: MarketConfig = field(default_factory=MarketConfig)
    chat: ChatConfig = field(default_factory=ChatConfig)
    emergency: EmergencyConfig = field(default_factory=EmergencyConfig)
    ui: UiConfig = field(default_factory=UiConfig)
    observability: ObservabilityConfig = field(default_factory=ObservabilityConfig)


# ── ConfigError ───────────────────────────────────────────────────────────────

class ConfigError(Exception):
    def __init__(self, code: str, **kwargs: object) -> None:
        super().__init__(code)
        self.code = code
        self.context = kwargs


# ── XDG path resolution ───────────────────────────────────────────────────────

def _xdg_data() -> Path:
    raw = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return Path(raw) / "hearthnet"


def _xdg_config() -> Path:
    raw = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return Path(raw) / "hearthnet"


def _xdg_cache() -> Path:
    raw = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    return Path(raw) / "hearthnet"


def _default_config_path() -> Path:
    return _xdg_config() / "config.toml"


# ── Path resolution ───────────────────────────────────────────────────────────

def resolve_paths(config: Config) -> Config:
    """Fill empty Path() fields with XDG-standard locations. Idempotent."""
    data = _xdg_data()
    cache = _xdg_cache()
    cfg = _xdg_config()

    identity = config.identity
    if identity.keys_dir == Path():
        identity = IdentityConfig(
            keys_dir=data / "keys",
            auto_generate=identity.auto_generate,
        )

    community = config.community
    if community.state_dir == Path():
        cid = community.community_id or "default"
        community = CommunityConfig(
            community_id=community.community_id,
            state_dir=data / "communities" / cid,
        )

    transport = config.transport
    tls_cert = transport.tls_cert or data / "tls" / "server.crt"
    tls_key = transport.tls_key or data / "tls" / "server.key"
    transport = TransportConfig(
        host=transport.host,
        port=transport.port,
        tls_cert=tls_cert,
        tls_key=tls_key,
    )

    rag = config.rag
    if rag.corpora_dir == Path():
        rag = RagConfig(enabled=rag.enabled, corpora_dir=cache / "embeddings")

    file_cfg = config.file
    if file_cfg.blobs_dir == Path():
        file_cfg = FileConfig(
            blobs_dir=data / "blobs",
            chunk_size_bytes=file_cfg.chunk_size_bytes,
            gc_threshold=file_cfg.gc_threshold,
        )

    obs = config.observability
    if obs.log_dir is None:
        obs = ObservabilityConfig(
            log_level=obs.log_level,
            log_dir=data / "logs",
            metrics_enabled=obs.metrics_enabled,
            otlp_endpoint=obs.otlp_endpoint,
        )

    return Config(
        identity=identity,
        community=community,
        transport=transport,
        discovery=config.discovery,
        bus=config.bus,
        llm=config.llm,
        embedding=config.embedding,
        rag=rag,
        file=file_cfg,
        market=config.market,
        chat=config.chat,
        emergency=config.emergency,
        ui=config.ui,
        observability=obs,
    )


# ── Validation ────────────────────────────────────────────────────────────────

def validate(config: Config) -> None:
    """Cross-field validation. Raises ConfigError on failure."""
    t = config.transport
    d = config.discovery
    if t.port == d.udp_port:
        raise ConfigError("invalid_field", field="transport.port/discovery.udp_port",
                          reason="transport port and UDP discovery port must differ")
    if not (1 <= t.port <= 65535):
        raise ConfigError("invalid_field", field="transport.port", reason="port out of range")
    if config.bus.local_load_threshold <= 0 or config.bus.local_load_threshold > 1:
        raise ConfigError("invalid_field", field="bus.local_load_threshold",
                          reason="must be in (0, 1]")


# ── TOML parsing helpers ──────────────────────────────────────────────────────

def _parse_toml(text: str) -> dict:
    if tomllib is None:
        raise ConfigError("invalid_toml", reason="no TOML parser available (install tomli)")
    try:
        return tomllib.loads(text)
    except Exception as exc:
        raise ConfigError("invalid_toml", reason=str(exc)) from exc


def _from_dict(raw: dict) -> Config:
    def _path(v: object) -> Path:
        return Path(v) if v else Path()

    identity_raw = raw.get("identity", {})
    identity = IdentityConfig(
        keys_dir=_path(identity_raw.get("keys_dir")),
        auto_generate=bool(identity_raw.get("auto_generate", True)),
    )

    community_raw = raw.get("community", {})
    community = CommunityConfig(
        community_id=community_raw.get("community_id") or None,
        state_dir=_path(community_raw.get("state_dir")),
    )

    transport_raw = raw.get("transport", {})
    transport = TransportConfig(
        host=str(transport_raw.get("host", "0.0.0.0")),
        port=int(transport_raw.get("port", HTTP_PORT)),
        tls_cert=_path(transport_raw.get("tls_cert")) or None,
        tls_key=_path(transport_raw.get("tls_key")) or None,
    )

    discovery_raw = raw.get("discovery", {})
    discovery = DiscoveryConfig(
        mdns_enabled=bool(discovery_raw.get("mdns_enabled", True)),
        udp_enabled=bool(discovery_raw.get("udp_enabled", True)),
        udp_port=int(discovery_raw.get("udp_port", 7079)),
        relay_urls=tuple(discovery_raw.get("relay_urls", [])),
    )

    bus_raw = raw.get("bus", {})
    bus = BusConfig(
        prefer_local=bool(bus_raw.get("prefer_local", True)),
        local_load_threshold=float(bus_raw.get("local_load_threshold", 0.80)),
    )

    llm_raw = raw.get("llm", {})
    backends = []
    for b in llm_raw.get("backends", []):
        backends.append(LlmBackendConfig(
            name=str(b["name"]),
            model=str(b.get("model", "")),
            base_url=str(b.get("base_url", "")),
            api_key_env=b.get("api_key_env") or None,
        ))
    llm = LlmConfig(backends=tuple(backends))

    embedding_raw = raw.get("embedding", {})
    embedding = EmbeddingConfig(
        model=str(embedding_raw.get("model", EMBED_DEFAULT_MODEL)),
        device=str(embedding_raw.get("device", "auto")),
    )

    rag_raw = raw.get("rag", {})
    rag = RagConfig(
        enabled=bool(rag_raw.get("enabled", True)),
        corpora_dir=_path(rag_raw.get("corpora_dir")),
    )

    file_raw = raw.get("file", {})
    file_cfg = FileConfig(
        blobs_dir=_path(file_raw.get("blobs_dir")),
        chunk_size_bytes=int(file_raw.get("chunk_size_bytes", CHUNK_SIZE_BYTES)),
        gc_threshold=float(file_raw.get("gc_threshold", 0.80)),
    )

    market_raw = raw.get("market", {})
    market = MarketConfig(
        enabled=bool(market_raw.get("enabled", True)),
        default_ttl_seconds=int(market_raw.get("default_ttl_seconds", MARKET_DEFAULT_TTL_SECONDS)),
        max_ttl_seconds=int(market_raw.get("max_ttl_seconds", MARKET_MAX_TTL_SECONDS)),
    )

    chat_raw = raw.get("chat", {})
    chat = ChatConfig(
        enabled=bool(chat_raw.get("enabled", True)),
        store_and_forward=bool(chat_raw.get("store_and_forward", True)),
        read_receipts_enabled=bool(chat_raw.get("read_receipts_enabled", True)),
    )

    emergency_raw = raw.get("emergency", {})
    emergency = EmergencyConfig(
        probe_targets=tuple(emergency_raw.get("probe_targets", [
            "1.1.1.1", "8.8.8.8", "https://cloudflare.com", "https://quad9.net",
        ])),
    )

    ui_raw = raw.get("ui", {})
    ui = UiConfig(
        host=str(ui_raw.get("host", "127.0.0.1")),
        port=int(ui_raw.get("port", UI_PORT)),
        launch_browser=bool(ui_raw.get("launch_browser", True)),
    )

    obs_raw = raw.get("observability", {})
    obs = ObservabilityConfig(
        log_level=str(obs_raw.get("log_level", "info")),
        log_dir=_path(obs_raw.get("log_dir")) or None,
        metrics_enabled=bool(obs_raw.get("metrics_enabled", True)),
        otlp_endpoint=obs_raw.get("otlp_endpoint") or None,
    )

    return Config(
        identity=identity,
        community=community,
        transport=transport,
        discovery=discovery,
        bus=bus,
        llm=llm,
        embedding=embedding,
        rag=rag,
        file=file_cfg,
        market=market,
        chat=chat,
        emergency=emergency,
        ui=ui,
        observability=obs,
    )


# ── Public API ────────────────────────────────────────────────────────────────

def default_config() -> Config:
    """Return a Config populated entirely from defaults."""
    return resolve_paths(Config())


def load(path: Path | None = None) -> Config:
    """Load from TOML file; apply defaults for omitted sections; validate."""
    cfg_path = path or _default_config_path()
    if not cfg_path.exists():
        cfg = default_config()
        validate(cfg)
        return cfg
    try:
        text = cfg_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError("path_resolution", reason=str(exc)) from exc
    raw = _parse_toml(text)
    cfg = resolve_paths(_from_dict(raw))
    validate(cfg)
    return cfg


def save(config: Config, path: Path | None = None) -> None:
    """Serialise config to TOML atomically."""
    import tempfile

    cfg_path = path or _default_config_path()
    cfg_path.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    lines.append("[identity]")
    lines.append(f'keys_dir = "{config.identity.keys_dir}"')
    lines.append(f"auto_generate = {str(config.identity.auto_generate).lower()}")
    lines.append("")
    lines.append("[community]")
    if config.community.community_id:
        lines.append(f'community_id = "{config.community.community_id}"')
    lines.append(f'state_dir = "{config.community.state_dir}"')
    lines.append("")
    lines.append("[transport]")
    lines.append(f'host = "{config.transport.host}"')
    lines.append(f"port = {config.transport.port}")
    if config.transport.tls_cert:
        lines.append(f'tls_cert = "{config.transport.tls_cert}"')
    if config.transport.tls_key:
        lines.append(f'tls_key = "{config.transport.tls_key}"')
    lines.append("")
    lines.append("[discovery]")
    lines.append(f"mdns_enabled = {str(config.discovery.mdns_enabled).lower()}")
    lines.append(f"udp_enabled = {str(config.discovery.udp_enabled).lower()}")
    lines.append(f"udp_port = {config.discovery.udp_port}")
    if config.discovery.relay_urls:
        urls = ", ".join(f'"{u}"' for u in config.discovery.relay_urls)
        lines.append(f"relay_urls = [{urls}]")
    lines.append("")
    lines.append("[bus]")
    lines.append(f"prefer_local = {str(config.bus.prefer_local).lower()}")
    lines.append(f"local_load_threshold = {config.bus.local_load_threshold}")
    lines.append("")
    lines.append("[embedding]")
    lines.append(f'model = "{config.embedding.model}"')
    lines.append(f'device = "{config.embedding.device}"')
    lines.append("")
    lines.append("[rag]")
    lines.append(f"enabled = {str(config.rag.enabled).lower()}")
    lines.append(f'corpora_dir = "{config.rag.corpora_dir}"')
    lines.append("")
    lines.append("[observability]")
    lines.append(f'log_level = "{config.observability.log_level}"')
    lines.append(f"metrics_enabled = {str(config.observability.metrics_enabled).lower()}")
    if config.observability.log_dir:
        lines.append(f'log_dir = "{config.observability.log_dir}"')

    content = "\n".join(lines) + "\n"
    fd, tmp = tempfile.mkstemp(dir=cfg_path.parent, prefix=".config_tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.replace(tmp, cfg_path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
