"""HearthNet — X03 Observability package.

Re-exports the public surface of all sub-modules so callers can do::

    from hearthnet.observability import get_logger, configure, new_trace, span

Full imports:
    from hearthnet.observability.logging import JsonFormatter, RateLimitedLogger
    from hearthnet.observability.metrics import counter, histogram, gauge
    from hearthnet.observability.tracing import Trace, Span, TraceRingBuffer
    from hearthnet.observability.doctor import run_all, run_one
"""

from __future__ import annotations

from hearthnet.observability.logging import (
    JsonFormatter,
    RateLimitedLogger,
    configure,
    get_logger,
)
from hearthnet.observability.tracing import (
    attach,
    current_trace,
    get_ring_buffer,
    new_trace,
    span,
)

__all__ = [
    "JsonFormatter",
    "RateLimitedLogger",
    # tracing
    "attach",
    # logging
    "configure",
    "current_trace",
    "get_logger",
    "get_ring_buffer",
    "new_trace",
    "span",
]
