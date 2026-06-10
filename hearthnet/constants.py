"""HearthNet — compile-time constants (numeric defaults, limits).

All module code that needs a tunable default imports from here.
Never hardcode these values inline.
"""
from __future__ import annotations

# ── Node manifest ────────────────────────────────────────────────────────────
MANIFEST_TTL_SECONDS: int = 30
MANIFEST_REFRESH_BEFORE_EXPIRY_SECONDS: int = 10

# ── Discovery ────────────────────────────────────────────────────────────────
MDNS_SERVICE_TYPE: str = "_hearthnet._tcp.local."
UDP_MULTICAST_GROUP: str = "224.0.0.251"
UDP_MULTICAST_PORT: int = 7079
UDP_ANNOUNCE_INTERVAL_ONLINE_SECONDS: int = 15
UDP_ANNOUNCE_INTERVAL_OFFLINE_SECONDS: int = 5
PEER_PRUNE_NORMAL_SECONDS: int = 90
PEER_PRUNE_AGGRESSIVE_SECONDS: int = 30
PEER_REFRESH_INTERVAL_SECONDS: int = 30

# ── Transport ────────────────────────────────────────────────────────────────
HTTP_PORT: int = 7080
UI_PORT: int = 7860
CONNECTION_IDLE_SECONDS: int = 60
RECONNECT_BACKOFF_CAP_SECONDS: int = 30
RATE_LIMIT_WINDOW_SECONDS: int = 60
RATE_LIMIT_MAX_CALLS: int = 200

# ── Bus ──────────────────────────────────────────────────────────────────────
BUS_HEALTH_WINDOW: int = 20          # samples per ring-buffer window
BUS_QUARANTINE_SECONDS: int = 60
BUS_FRESHNESS_SECONDS: int = 60
BUS_LOCAL_LOAD_THRESHOLD: float = 0.80

# ── Emergency detector ───────────────────────────────────────────────────────
EMERGENCY_PROBE_INTERVAL_ONLINE_SECONDS: int = 30
EMERGENCY_PROBE_INTERVAL_OFFLINE_SECONDS: int = 10
EMERGENCY_PROBE_TIMEOUT_SECONDS: int = 5
EMERGENCY_TRANSITION_DEBOUNCE_SECONDS: int = 5
EMERGENCY_ANTI_FLAP_WINDOW_SECONDS: int = 60
EMERGENCY_ANTI_FLAP_MAX_TRANSITIONS: int = 3
EMERGENCY_CLOCK_SKEW_WARN_SECONDS: int = 60

# ── Blobs ─────────────────────────────────────────────────────────────────────
CHUNK_SIZE_BYTES: int = 256 * 1024  # 256 KB
BLOB_GC_THRESHOLD: float = 0.80

# ── Events / Lamport ─────────────────────────────────────────────────────────
SNAPSHOT_KEEP_LAST_N: int = 7

# ── Observability ─────────────────────────────────────────────────────────────
LOG_RETENTION_DAYS: int = 14
TRACE_RING_BUFFER_SIZE: int = 1000

# ── Onboarding ───────────────────────────────────────────────────────────────
INVITE_DEFAULT_TTL_SECONDS: int = 86400   # 24 h

# ── RAG / Embedding ──────────────────────────────────────────────────────────
RAG_DEFAULT_CHUNK_SIZE_TOKENS: int = 512

# ── Rerank ────────────────────────────────────────────────────────────────────
RERANK_MAX_DOCS: int = 100
RERANK_LOAD_TIMEOUT_SECONDS: int = 60
EMBED_MAX_TEXTS: int = 256
EMBED_MAX_CHARS: int = 8192
RAG_OVERLAP_TOKENS: int = 64
EMBED_MAX_TEXTS: int = 256
EMBED_MAX_CHARS: int = 8192
EMBED_DEFAULT_MODEL: str = "BAAI/bge-small-en-v1.5"

# ── LLM ──────────────────────────────────────────────────────────────────────
LLM_STREAM_CANCEL_TIMEOUT_MS: int = 200

# ── Marketplace ──────────────────────────────────────────────────────────────
MARKET_SWEEP_INTERVAL_SECONDS: int = 60
MARKET_DEFAULT_TTL_SECONDS: int = 86400 * 7   # 1 week
MARKET_MAX_TTL_SECONDS: int = 86400 * 30      # 30 days
MARKET_SEARCH_CACHE_MAX: int = 5000

# ── STT / TTS ─────────────────────────────────────────────────────────────────
STT_MAX_AUDIO_SECONDS: int = 300

# ── Translation ───────────────────────────────────────────────────────────────
TRANSLATION_MAX_CHARS: int = 4000

# ── Rerank ────────────────────────────────────────────────────────────────────
RERANK_MAX_DOCS: int = 100
