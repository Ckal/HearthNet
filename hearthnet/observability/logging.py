"""HearthNet — X03 Observability: Structured JSON logging.

Public API:
    configure(config)   — install handlers/formatters. Idempotent.
    get_logger(name)    — return JSON-emitting stdlib logger
    JsonFormatter       — one-line JSON log records
    RateLimitedLogger   — at most one log per second per (logger, key)
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import threading
import time
from pathlib import Path
from typing import Any

from hearthnet.config import ObservabilityConfig
from hearthnet.constants import LOG_RETENTION_DAYS

_configured = False
_configure_lock = threading.Lock()


class JsonFormatter(logging.Formatter):
    """Renders a LogRecord as a single JSON line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S.") + f"{record.msecs:03.0f}Z",
            "level": record.levelname.lower(),
            "logger": record.name,
            "msg": record.getMessage(),
        }

        # Attach structured extras (skip stdlib internals)
        _SKIP = {
            "name",
            "msg",
            "args",
            "created",
            "filename",
            "funcName",
            "levelname",
            "levelno",
            "lineno",
            "module",
            "msecs",
            "pathname",
            "process",
            "processName",
            "relativeCreated",
            "stack_info",
            "thread",
            "threadName",
            "exc_info",
            "exc_text",
            "message",
        }
        payload.update({key: val for key, val in record.__dict__.items() if key not in _SKIP})

        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str, ensure_ascii=False)


def configure(config: ObservabilityConfig) -> None:
    """Install handlers and formatters on the root 'hearthnet' logger.

    Idempotent — safe to call multiple times; only runs once.
    """
    global _configured
    with _configure_lock:
        if _configured:
            return
        _configured = True

    level_name = (config.log_level or "info").upper()
    level = getattr(logging, level_name, logging.INFO)

    root = logging.getLogger("hearthnet")
    root.setLevel(level)
    root.handlers.clear()  # reset on reconfigure

    formatter = JsonFormatter()

    # Console handler
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(console)

    # File handler (daily rotation, 14-day retention)
    log_dir: Path | None = config.log_dir
    if log_dir is not None:
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "hearthnet.log"
        file_handler = logging.handlers.TimedRotatingFileHandler(
            filename=str(log_path),
            when="midnight",
            utc=True,
            backupCount=LOG_RETENTION_DAYS,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

    root.propagate = False


def get_logger(name: str) -> logging.Logger:
    """Return a stdlib logger that emits JSON lines.

    Convention: ``name = __name__`` of the calling module.
    """
    return logging.getLogger(name)


class RateLimitedLogger:
    """Wraps a Logger and suppresses duplicate messages within a 1-second window.

    Keyed by ``(logger_name, message_key)`` — call with an explicit *key*
    argument to group semantically similar messages:

        rl_log.warning("peer unreachable", key="peer_unreachable")
    """

    def __init__(self, logger: logging.Logger) -> None:
        self._logger = logger
        self._last: dict[tuple[str, str], float] = {}
        self._lock = threading.Lock()
        self._window = 1.0  # seconds

    def _should_emit(self, key: str) -> bool:
        bucket = (self._logger.name, key)
        now = time.monotonic()
        with self._lock:
            last = self._last.get(bucket, 0.0)
            if now - last >= self._window:
                self._last[bucket] = now
                return True
        return False

    def _emit(self, level: int, msg: str, key: str, **kwargs: Any) -> None:
        if self._should_emit(key):
            self._logger.log(level, msg, **kwargs)

    def debug(self, msg: str, *, key: str = "", **kwargs: Any) -> None:
        self._emit(logging.DEBUG, msg, key or msg, **kwargs)

    def info(self, msg: str, *, key: str = "", **kwargs: Any) -> None:
        self._emit(logging.INFO, msg, key or msg, **kwargs)

    def warning(self, msg: str, *, key: str = "", **kwargs: Any) -> None:
        self._emit(logging.WARNING, msg, key or msg, **kwargs)

    def error(self, msg: str, *, key: str = "", **kwargs: Any) -> None:
        self._emit(logging.ERROR, msg, key or msg, **kwargs)
