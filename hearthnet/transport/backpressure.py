"""X01 — Backpressure / flow control.

Spec: docs/X01-transport.md §3.4

FlowControl gates outbound work when a downstream consumer is slow.
Used by HttpServer SSE streams and WebSocket pub-sub to avoid unbounded queues.
"""

from __future__ import annotations

import asyncio


class FlowControl:
    """Leaky-bucket / semaphore flow control for streaming responses.

    Usage::

        fc = FlowControl(capacity=32)
        async with fc.acquire():
            await stream_chunk(data)

    If the number of in-flight chunks reaches *capacity*, ``acquire()``
    blocks until a slot is freed.  This creates natural back-pressure so
    a slow HTTP client cannot cause the server to buffer unbounded data.
    """

    def __init__(self, capacity: int = 64) -> None:
        if capacity < 1:
            raise ValueError("capacity must be >= 1")
        self._sem = asyncio.Semaphore(capacity)
        self._capacity = capacity
        self._total_acquired: int = 0
        self._total_released: int = 0

    @property
    def capacity(self) -> int:
        return self._capacity

    @property
    def in_flight(self) -> int:
        return self._total_acquired - self._total_released

    def acquire(self) -> _AcquireContext:
        return _AcquireContext(self)

    async def _acquire(self) -> None:
        await self._sem.acquire()
        self._total_acquired += 1

    def _release(self) -> None:
        self._sem.release()
        self._total_released += 1

    def stats(self) -> dict:
        return {
            "capacity": self._capacity,
            "in_flight": self.in_flight,
            "total_acquired": self._total_acquired,
            "total_released": self._total_released,
        }


class _AcquireContext:
    def __init__(self, fc: FlowControl) -> None:
        self._fc = fc

    async def __aenter__(self) -> _AcquireContext:
        await self._fc._acquire()
        return self

    async def __aexit__(self, *_) -> None:
        self._fc._release()


# ---------------------------------------------------------------------------
# RateCheck / RateLimiter (X01 §3.5)
# ---------------------------------------------------------------------------


class RateCheck:
    """Simple sliding-window rate check (read-only, no blocking).

    Use to check whether a call is within limits before proceeding.
    Returns True if allowed, False if over limit.
    """

    def __init__(self, max_calls: int, window_seconds: float = 1.0) -> None:
        self._max = max_calls
        self._window = window_seconds
        self._calls: list[float] = []

    def check(self, now: float | None = None) -> bool:
        import time
        t = now if now is not None else time.monotonic()
        cutoff = t - self._window
        self._calls = [c for c in self._calls if c > cutoff]
        if len(self._calls) < self._max:
            self._calls.append(t)
            return True
        return False

    def reset(self) -> None:
        self._calls.clear()


class RateLimiter:
    """Async rate limiter — blocks until a slot is available.

    Usage::

        rl = RateLimiter(max_calls=10, window_seconds=1.0)
        await rl.acquire()
        # ... do work ...
    """

    def __init__(self, max_calls: int, window_seconds: float = 1.0) -> None:
        self._max = max_calls
        self._window = window_seconds
        self._calls: list[float] = []
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        import time
        while True:
            async with self._lock:
                t = time.monotonic()
                cutoff = t - self._window
                self._calls = [c for c in self._calls if c > cutoff]
                if len(self._calls) < self._max:
                    self._calls.append(t)
                    return
            await asyncio.sleep(self._window / self._max)
