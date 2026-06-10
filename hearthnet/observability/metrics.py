"""HearthNet — X03 Observability: Prometheus-compatible metrics.

prometheus_client is OPTIONAL. When not installed every factory returns a
no-op object so call sites need no conditional logic.

Public API:
    configure(config)   — initialise registries / start HTTP endpoint
    counter(...)        — Counter factory
    histogram(...)      — Histogram factory
    gauge(...)          — Gauge factory
    disabled() -> bool  — True when prometheus_client is absent or metrics off

Standard HearthNet metrics are created at module import time so they are
always available as module-level names.
"""
from __future__ import annotations

import threading
from typing import Any

from hearthnet.config import ObservabilityConfig

# ── Optional prometheus_client import ───────────────────────────────────────

try:
    import prometheus_client as _prom  # type: ignore[import]
    _PROM_AVAILABLE = True
except ImportError:  # pragma: no cover
    _prom = None  # type: ignore[assignment]
    _PROM_AVAILABLE = False

_metrics_enabled: bool = True
_configure_lock = threading.Lock()
_configured = False


# ── No-op stubs ──────────────────────────────────────────────────────────────

class _NoOpMetric:
    """Returned in place of a real Prometheus metric when unavailable."""

    def labels(self, **_kwargs: Any) -> "_NoOpMetric":
        return self

    def inc(self, *_a: Any, **_kw: Any) -> None:
        pass

    def observe(self, *_a: Any, **_kw: Any) -> None:
        pass

    def set(self, *_a: Any, **_kw: Any) -> None:
        pass


_NOOP = _NoOpMetric()


# ── Factories ────────────────────────────────────────────────────────────────

def disabled() -> bool:
    """Return True when metrics collection is not active."""
    return not (_PROM_AVAILABLE and _metrics_enabled)


def counter(
    name: str,
    doc: str,
    labels: list[str] | None = None,
) -> Any:
    """Return a prometheus_client Counter or a no-op."""
    if disabled():
        return _NOOP
    try:
        return _prom.Counter(name, doc, labels or [])
    except Exception:
        return _NOOP


def histogram(
    name: str,
    doc: str,
    labels: list[str] | None = None,
    buckets: list[float] | None = None,
) -> Any:
    """Return a prometheus_client Histogram or a no-op."""
    if disabled():
        return _NOOP
    kwargs: dict[str, Any] = {}
    if buckets is not None:
        kwargs["buckets"] = buckets
    try:
        return _prom.Histogram(name, doc, labels or [], **kwargs)
    except Exception:
        return _NOOP


def gauge(
    name: str,
    doc: str,
    labels: list[str] | None = None,
) -> Any:
    """Return a prometheus_client Gauge or a no-op."""
    if disabled():
        return _NOOP
    try:
        return _prom.Gauge(name, doc, labels or [])
    except Exception:
        return _NOOP


def configure(config: ObservabilityConfig) -> None:
    """Initialise metrics according to *config*. Idempotent."""
    global _metrics_enabled, _configured
    with _configure_lock:
        if _configured:
            return
        _configured = True
        _metrics_enabled = config.metrics_enabled


# ── Standard HearthNet metrics ───────────────────────────────────────────────
# Created lazily to avoid side-effects at import time when prometheus_client
# is not installed. Exposed as module-level singletons.

_STD: dict[str, Any] = {}
_std_lock = threading.Lock()


def _std(name: str, kind: str, doc: str, labels: list[str], **kw: Any) -> Any:
    """Return (and memoize) a named standard metric."""
    with _std_lock:
        if name not in _STD:
            if kind == "counter":
                _STD[name] = counter(name, doc, labels)
            elif kind == "histogram":
                _STD[name] = histogram(name, doc, labels, **kw)
            else:
                _STD[name] = gauge(name, doc, labels)
        return _STD[name]


# Convenience accessors for standard metrics -----------------------------------

def requests_total() -> Any:
    return _std(
        "hearthnet_requests_total", "counter",
        "Total routed requests", ["capability", "result"],
    )


def request_duration_ms() -> Any:
    return _std(
        "hearthnet_request_duration_ms", "histogram",
        "Request round-trip duration in milliseconds", ["capability"],
        buckets=[5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000],
    )


def active_streams() -> Any:
    return _std(
        "hearthnet_active_streams", "gauge",
        "Currently open streaming requests", ["capability"],
    )


def nodes_online() -> Any:
    return _std(
        "hearthnet_nodes_online", "gauge",
        "Known online nodes per community", ["community"],
    )


def event_log_size() -> Any:
    return _std(
        "hearthnet_event_log_size", "gauge",
        "Number of entries in the event log", ["community"],
    )


def emergency_mode() -> Any:
    return _std(
        "hearthnet_emergency_mode", "gauge",
        "Whether emergency mode is active (1) or not (0)", ["state"],
    )


def blob_storage_bytes() -> Any:
    return _std(
        "hearthnet_blob_storage_bytes", "gauge",
        "Total bytes stored in the blob store", [],
    )


def llm_tokens_generated_total() -> Any:
    return _std(
        "hearthnet_llm_tokens_generated_total", "counter",
        "LLM tokens generated since startup", ["model", "backend"],
    )


def capability_health_success_rate() -> Any:
    return _std(
        "hearthnet_capability_health_success_rate", "gauge",
        "Rolling success rate for a capability on a given node", ["capability", "node"],
    )


def signature_failures_total() -> Any:
    return _std(
        "hearthnet_signature_failures_total", "counter",
        "Signature verification failures", ["reason"],
    )
