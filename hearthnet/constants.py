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
BUS_HEALTH_WINDOW: int = 20  # samples per ring-buffer window
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
INVITE_DEFAULT_TTL_SECONDS: int = 86400  # 24 h

# ── RAG / Embedding ──────────────────────────────────────────────────────────
RAG_DEFAULT_CHUNK_SIZE_TOKENS: int = 512

# ── Rerank ────────────────────────────────────────────────────────────────────
RERANK_MAX_DOCS: int = 100
RERANK_LOAD_TIMEOUT_SECONDS: int = 60
EMBED_MAX_TEXTS: int = 256
EMBED_MAX_CHARS: int = 8192
RAG_OVERLAP_TOKENS: int = 64
EMBED_DEFAULT_MODEL: str = "BAAI/bge-small-en-v1.5"

# ── LLM ──────────────────────────────────────────────────────────────────────
LLM_STREAM_CANCEL_TIMEOUT_MS: int = 200

# ── Marketplace ──────────────────────────────────────────────────────────────
MARKET_SWEEP_INTERVAL_SECONDS: int = 60
MARKET_DEFAULT_TTL_SECONDS: int = 86400 * 7  # 1 week
MARKET_MAX_TTL_SECONDS: int = 86400 * 30  # 30 days
MARKET_SEARCH_CACHE_MAX: int = 5000

# ── STT / TTS ─────────────────────────────────────────────────────────────────
STT_MAX_AUDIO_SECONDS: int = 300

# ── Translation ───────────────────────────────────────────────────────────────
TRANSLATION_MAX_CHARS: int = 4000

# ── Distributed inference (M26) ───────────────────────────────────────────────
DISTRIBUTED_LLM_MAX_SHARDS_PER_PIPELINE: int = 16
DISTRIBUTED_LLM_SHARD_HEARTBEAT_SECONDS: int = 5
DISTRIBUTED_LLM_FAILOVER_TIMEOUT_SECONDS: int = 10
DISTRIBUTED_LLM_MAX_PIPELINE_LATENCY_TOKENS_PER_S: float = 2.0  # advisory floor
DISTRIBUTED_LLM_DEFAULT_DTYPE: str = "fp16"
DISTRIBUTED_MAX_SHARDS_PER_REQUEST: int = 16
DISTRIBUTED_SHARD_HEALTH_TIMEOUT_S: int = 30
DISTRIBUTED_FALLBACK_TO_LOCAL_AFTER_FAILURES: int = 2

# ── MoE routing (M27) ────────────────────────────────────────────────────────
MOE_TOP_K_DEFAULT: int = 3
MOE_LEARNED_SCORER_MIN_FEEDBACK_SAMPLES: int = 200
MOE_HUMAN_HANDOFF_DEFAULT_TIMEOUT_HOURS: int = 24
MOE_HUMAN_HANDOFF_COOLDOWN_HOURS: int = 2
MOE_HUMAN_RATE_LIMIT_PER_DAY: int = 5
MOE_ROUTER_TOP_K: int = 3
MOE_ROUTER_TRAIN_MIN_EXAMPLES: int = 200
MOE_ROUTER_RETRAIN_EVERY_HOURS: int = 24

# ── Federated learning (M28) ─────────────────────────────────────────────────
FEDLEARN_MAX_LORA_RANK: int = 64
FEDLEARN_MAX_LORA_TARGET_MODULES: int = 8
FEDLEARN_MAX_TRAIN_STEPS: int = 1000
FEDLEARN_MAX_PARTICIPANTS: int = 32
FEDLEARN_MIN_PARTICIPANTS: int = 3
FEDLEARN_DP_NOISE_SCALE_DEFAULT: float = 0.0  # off — off-by-default differential privacy
FEDLEARN_CLIP_NORM_DEFAULT: float = 1.0
FEDLEARN_SUBMISSION_MAX_BYTES: int = 64 * 1024 * 1024
FEDLEARN_MAX_ROUND_MINUTES: int = 120
FEDLEARN_GRAD_CLIP: float = 1.0

# ── LoRa beacons (M29) ───────────────────────────────────────────────────────
LORA_BEACON_PERIOD_SECONDS_DEFAULT: int = 600  # 10 min
LORA_BEACON_MAX_PAYLOAD_BYTES: int = 32
LORA_RX_QUEUE_MAX: int = 256
LORA_PEER_RX_MAX_PER_MINUTE: int = 20
LORA_PANIC_BURST_COUNT: int = 3
LORA_PANIC_BURST_GAP_MS: int = 800

# ── Evidence graph (M30) ─────────────────────────────────────────────────────
EVIDENCE_CLAIM_TTL_DAYS_DEFAULT: int = 365
EVIDENCE_DISPUTE_MIN_TRUST: float = 0.3
EVIDENCE_MAX_PROVENANCE_DEPTH: int = 8

# ── Civil defense (M31) ──────────────────────────────────────────────────────
CIVDEF_AUDIT_RETENTION_YEARS: int = 10  # operator must validate against local law
CIVDEF_ACK_MAX_PER_MINUTE_PER_NODE: int = 5
CIVDEF_ALERT_TITLE_MAX_CHARS: int = 80
CIVDEF_ALERT_BODY_MAX_CHARS: int = 1000
CIVDEF_HEARTBEAT_SECONDS: int = 60

# ── Tensor transport (X08) ───────────────────────────────────────────────────
TENSOR_CHUNK_BYTES: int = 1 * 1024 * 1024       # 1 MiB
TENSOR_FLOW_CONTROL_WINDOW: int = 16
TENSOR_COMPRESSION_THRESHOLD_BYTES: int = 64 * 1024
TENSOR_KEEPALIVE_SECONDS: int = 30
TENSOR_MAX_SESSION_LIFETIME_SECONDS: int = 3600

# ── Conformance suite (X09) ──────────────────────────────────────────────────
CONFORMANCE_DEFAULT_SEED: int = 0xC0FFEE
CONFORMANCE_DEFAULT_OUTPUT_DIR: str = "./conformance-report"
