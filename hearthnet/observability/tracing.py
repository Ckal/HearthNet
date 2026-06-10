"""HearthNet — X03 Observability: Per-request tracing.

Uses contextvars.ContextVar so traces propagate correctly across asyncio tasks.

Public API:
    new_trace(capability)  — create and attach a fresh Trace
    current_trace()        — return the active Trace or None
    attach(trace)          — set the active Trace on this context
    span(name, **extras)   — context-manager that records a Span
    TraceRingBuffer        — thread-safe ring buffer of last N traces
    get_ring_buffer()      — module-level singleton ring buffer
"""

from __future__ import annotations

import secrets
import threading
import time
from collections import deque
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field

from hearthnet.constants import TRACE_RING_BUFFER_SIZE

# ── ULID approximation ───────────────────────────────────────────────────────


def _new_ulid() -> str:
    """Simple ULID approximation: 13-digit ms timestamp + 12 hex random chars."""
    try:
        from python_ulid import ULID  # type: ignore[import]

        return str(ULID())
    except ImportError:
        ts = str(int(time.time() * 1000)).zfill(13)
        rand = secrets.token_hex(6).upper()
        return ts + rand


# ── Dataclasses ──────────────────────────────────────────────────────────────


@dataclass
class Span:
    name: str
    started_at: float = field(default_factory=time.monotonic)
    ended_at: float | None = None
    extras: dict = field(default_factory=dict)

    @property
    def duration_ms(self) -> float | None:
        if self.ended_at is None:
            return None
        return (self.ended_at - self.started_at) * 1000.0


@dataclass
class Trace:
    trace_id: str = field(default_factory=_new_ulid)
    capability: str = ""
    started_at: float = field(default_factory=time.monotonic)
    spans: list[Span] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def add_span(self, span: Span) -> None:
        with self._lock:
            self.spans.append(span)


# ── Context variable ─────────────────────────────────────────────────────────

_current_trace: ContextVar[Trace | None] = ContextVar("_current_trace", default=None)


# ── Public API ───────────────────────────────────────────────────────────────


def new_trace(capability: str) -> Trace:
    """Create a fresh Trace, attach it to this context, and return it."""
    trace = Trace(capability=capability)
    _current_trace.set(trace)
    get_ring_buffer().push(trace)
    return trace


def current_trace() -> Trace | None:
    """Return the Trace active on this context, or None."""
    return _current_trace.get()


def attach(trace: Trace) -> None:
    """Set *trace* as the active trace on this context (e.g. to propagate to a child task)."""
    _current_trace.set(trace)


@contextmanager
def span(name: str, **extras: object) -> Iterator[Span]:
    """Context-manager that records a Span on the current Trace (if any).

    Usage::

        async with span("embed", model="nomic"):
            ...
    """
    s = Span(name=name, extras=dict(extras))
    trace = current_trace()
    try:
        yield s
    finally:
        s.ended_at = time.monotonic()
        if trace is not None:
            trace.add_span(s)


# ── Ring buffer ──────────────────────────────────────────────────────────────


class TraceRingBuffer:
    """Thread-safe bounded ring buffer that keeps the last *maxlen* traces."""

    def __init__(self, maxlen: int = TRACE_RING_BUFFER_SIZE) -> None:
        self._buf: deque[Trace] = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def push(self, trace: Trace) -> None:
        with self._lock:
            self._buf.append(trace)

    def snapshot(self) -> list[Trace]:
        """Return a copy of all buffered traces, oldest first."""
        with self._lock:
            return list(self._buf)

    def __len__(self) -> int:
        with self._lock:
            return len(self._buf)


_ring_buffer: TraceRingBuffer | None = None
_ring_lock = threading.Lock()


def get_ring_buffer() -> TraceRingBuffer:
    """Return the module-level singleton TraceRingBuffer."""
    global _ring_buffer
    if _ring_buffer is None:
        with _ring_lock:
            if _ring_buffer is None:
                _ring_buffer = TraceRingBuffer()
    return _ring_buffer
