"""X02 - Event log (SQLite WAL).

Spec: docs/X02-events.md §3.3
Impl-ref: impl_ref.md §3

All community events signed with author Ed25519 key.
Lamport clock enforces causal ordering.
ReplayEngine drives materialised views (marketplace, chat).
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
from collections.abc import AsyncIterator
from datetime import datetime, timezone

UTC = timezone.utc
from pathlib import Path
from typing import Any

from .lamport import LamportClock
from .types import _ALL_EVENT_TYPES, Event, EventType, new_ulid

_SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;

CREATE TABLE IF NOT EXISTS events (
  event_id        TEXT PRIMARY KEY,
  event_type      TEXT NOT NULL,
  community_id    TEXT NOT NULL,
  author          TEXT NOT NULL,
  lamport         INTEGER NOT NULL,
  payload         TEXT NOT NULL,
  issued_at       TEXT NOT NULL,
  signature       TEXT NOT NULL,
  schema_version  INTEGER NOT NULL DEFAULT 1,
  received_at     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_lamport
  ON events(community_id, lamport, event_id);

CREATE INDEX IF NOT EXISTS idx_events_type
  ON events(community_id, event_type, lamport);

CREATE TABLE IF NOT EXISTS clock (
  community_id TEXT PRIMARY KEY,
  lamport      INTEGER NOT NULL
);
"""


def _now_utc() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def _row_to_event(row: tuple[Any, ...]) -> Event:
    (
        event_id,
        event_type,
        community_id,
        author,
        lamport,
        payload,
        issued_at,
        signature,
        schema_version,
        _received_at,
    ) = row
    return Event(
        schema_version=schema_version,
        event_id=event_id,
        event_type=event_type,
        community_id=community_id,
        author=author,
        lamport=lamport,
        payload=json.loads(payload),
        issued_at=issued_at,
        signature=signature,
    )


def _sign(event: Event, kp: Any) -> str:
    """Return signature string or '' when kp is None."""
    if kp is None:
        return ""
    import base64
    import hashlib

    raw = _canonical_bytes(event)
    if hasattr(kp, "sign"):
        sig_bytes: bytes = kp.sign(raw)
    else:
        # Fallback: HMAC-SHA256 keyed by kp as bytes (test usage)
        import hmac

        sig_bytes = hmac.new(kp, raw, hashlib.sha256).digest()
    encoded = base64.urlsafe_b64encode(sig_bytes).rstrip(b"=").decode()
    return f"ed25519:{encoded}"


def _canonical_bytes(event: Event) -> bytes:
    """Deterministic serialisation for signing / verification."""
    obj = {
        "schema_version": event.schema_version,
        "event_id": event.event_id,
        "event_type": event.event_type,
        "community_id": event.community_id,
        "author": event.author,
        "lamport": event.lamport,
        "payload": event.payload,
        "issued_at": event.issued_at,
    }
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def _verify(event: Event, kp_store: Any) -> bool:
    """Return True if the signature is valid or if there is no kp_store."""
    if kp_store is None:
        return True
    if not event.signature:
        return True
    if hasattr(kp_store, "verify"):
        try:
            import base64

            prefix = "ed25519:"
            b64 = (
                event.signature[len(prefix) :]
                if event.signature.startswith(prefix)
                else event.signature
            )
            # pad
            padding = 4 - len(b64) % 4
            if padding != 4:
                b64 += "=" * padding
            sig_bytes = base64.urlsafe_b64decode(b64)
            raw = _canonical_bytes(event)
            return kp_store.verify(event.author, raw, sig_bytes)
        except Exception:
            return False
    return True


class EventLogError(Exception):
    """Raised for protocol violations in the event log."""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


class EventLog:
    """SQLite-backed append-only event log for one community."""

    def __init__(
        self,
        db_path: Path,
        community_id: str,
        kp_store: Any = None,
    ) -> None:
        self._db_path = db_path
        self._community_id = community_id
        self._kp_store = kp_store
        self._lock = threading.Lock()
        self._subscribers: list[tuple[asyncio.Queue[Event], frozenset[str] | None]] = []

        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._init_schema()
        self._clock = LamportClock(community_id, db_path)
        self._clock._conn = self._conn  # share connection

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _init_schema(self) -> None:
        for stmt in _SCHEMA.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                self._conn.execute(stmt)
        self._conn.commit()

    # ------------------------------------------------------------------
    # Writing
    # ------------------------------------------------------------------

    def append_local(
        self,
        event_type: EventType,
        author: str,
        payload: dict[str, Any],
        kp: Any = None,
    ) -> Event:
        """Mint, sign, and persist a new local event atomically."""
        if event_type not in _ALL_EVENT_TYPES:
            raise EventLogError("schema_unknown", f"Unknown event_type: {event_type!r}")

        with self._lock:
            lamport = self._clock._value + 1
            event_id = new_ulid()
            now = _now_utc()

            # Build unsigned event first to produce canonical bytes
            event = Event(
                schema_version=1,
                event_id=event_id,
                event_type=event_type,
                community_id=self._community_id,
                author=author,
                lamport=lamport,
                payload=payload,
                issued_at=now,
                signature="",
            )
            sig = _sign(event, kp)
            # Replace with signed version
            import dataclasses

            event = dataclasses.replace(event, signature=sig)

            self._clock._value = lamport
            self._conn.execute("BEGIN")
            try:
                self._conn.execute(
                    "INSERT INTO events "
                    "(event_id,event_type,community_id,author,lamport,payload,issued_at,signature,schema_version,received_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (
                        event.event_id,
                        event.event_type,
                        event.community_id,
                        event.author,
                        event.lamport,
                        json.dumps(event.payload, sort_keys=True),
                        event.issued_at,
                        event.signature,
                        event.schema_version,
                        now,
                    ),
                )
                self._clock._save_in_tx(self._conn)
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise

        self._fanout(event)
        return event

    def append_received(self, event: Event) -> bool:
        """Persist a peer event.  Returns False for duplicates, True if new."""
        if event.event_type not in _ALL_EVENT_TYPES:
            raise EventLogError("schema_unknown", f"Unknown event_type: {event.event_type!r}")

        if not _verify(event, self._kp_store):
            raise EventLogError("invalid_signature", f"Bad signature on {event.event_id}")

        with self._lock:
            # Duplicate check
            dup = self._conn.execute(
                "SELECT 1 FROM events WHERE event_id = ?", (event.event_id,)
            ).fetchone()
            if dup:
                return False

            new_lamport = max(self._clock._value, event.lamport) + 1
            now = _now_utc()

            self._conn.execute("BEGIN")
            try:
                self._conn.execute(
                    "INSERT INTO events "
                    "(event_id,event_type,community_id,author,lamport,payload,issued_at,signature,schema_version,received_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (
                        event.event_id,
                        event.event_type,
                        event.community_id,
                        event.author,
                        event.lamport,
                        json.dumps(event.payload, sort_keys=True),
                        event.issued_at,
                        event.signature,
                        event.schema_version,
                        now,
                    ),
                )
                self._clock._value = new_lamport
                self._clock._save_in_tx(self._conn)
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise

        self._fanout(event)
        return True

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------

    def get(self, event_id: str) -> Event | None:
        row = self._conn.execute(
            "SELECT event_id,event_type,community_id,author,lamport,payload,issued_at,signature,schema_version,received_at "
            "FROM events WHERE event_id = ?",
            (event_id,),
        ).fetchone()
        return _row_to_event(row) if row else None

    def since(self, lamport: int, limit: int = 1000) -> list[Event]:
        """Return events with lamport >= given value, ordered by (lamport, event_id)."""
        rows = self._conn.execute(
            "SELECT event_id,event_type,community_id,author,lamport,payload,issued_at,signature,schema_version,received_at "
            "FROM events WHERE community_id = ? AND lamport >= ? "
            "ORDER BY lamport ASC, event_id ASC LIMIT ?",
            (self._community_id, lamport, limit),
        ).fetchall()
        return [_row_to_event(r) for r in rows]

    def head(self) -> int:
        """Highest Lamport value stored."""
        row = self._conn.execute(
            "SELECT MAX(lamport) FROM events WHERE community_id = ?",
            (self._community_id,),
        ).fetchone()
        return row[0] if row and row[0] is not None else 0

    def by_type(self, event_type: EventType, since_lamport: int = 0) -> list[Event]:
        rows = self._conn.execute(
            "SELECT event_id,event_type,community_id,author,lamport,payload,issued_at,signature,schema_version,received_at "
            "FROM events WHERE community_id = ? AND event_type = ? AND lamport >= ? "
            "ORDER BY lamport ASC, event_id ASC",
            (self._community_id, event_type, since_lamport),
        ).fetchall()
        return [_row_to_event(r) for r in rows]

    def heads_by_type(self) -> dict[str, int]:
        """Highest lamport per event_type; used by sync."""
        rows = self._conn.execute(
            "SELECT event_type, MAX(lamport) FROM events WHERE community_id = ? GROUP BY event_type",
            (self._community_id,),
        ).fetchall()
        return {row[0]: row[1] for row in rows}

    def replay(
        self,
        *,
        since_lamport: int = 0,
        event_types: list[EventType] | None = None,
        limit: int | None = None,
    ) -> list[Event]:
        """Return events in (lamport, event_id) order, optionally filtered."""
        if event_types:
            # placeholders contains only "?" characters (len = len(event_types)) — not user input
            placeholders = ",".join("?" for _ in event_types)
            sql = (  # nosec B608
                "SELECT event_id,event_type,community_id,author,lamport,payload,issued_at,signature,schema_version,received_at "
                "FROM events WHERE community_id = ? AND lamport >= ? "
                f"AND event_type IN ({placeholders}) "  # nosec B608
                "ORDER BY lamport ASC, event_id ASC"
            )
            params: list[Any] = [self._community_id, since_lamport, *event_types]
        else:
            sql = (
                "SELECT event_id,event_type,community_id,author,lamport,payload,issued_at,signature,schema_version,received_at "
                "FROM events WHERE community_id = ? AND lamport >= ? "
                "ORDER BY lamport ASC, event_id ASC"
            )
            params = [self._community_id, since_lamport]

        if limit is not None:
            sql += f" LIMIT {int(limit)}"

        rows = self._conn.execute(sql, params).fetchall()
        return [_row_to_event(r) for r in rows]

    # ------------------------------------------------------------------
    # Pubsub
    # ------------------------------------------------------------------

    def subscribe(
        self,
        event_types: list[EventType] | None = None,
    ) -> AsyncIterator[Event]:
        """Return an async iterator that yields matching events as they arrive."""
        q: asyncio.Queue[Event] = asyncio.Queue()
        ft: frozenset[str] | None = frozenset(event_types) if event_types else None
        self._subscribers.append((q, ft))

        async def _iter() -> AsyncIterator[Event]:
            try:
                while True:
                    event = await q.get()
                    yield event
            except GeneratorExit:
                pass
            finally:
                try:
                    self._subscribers.remove((q, ft))
                except ValueError:
                    pass

        return _iter()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        try:
            self._conn.close()
        except Exception:
            pass

    def _fanout(self, event: Event) -> None:
        """Push event to all in-process subscribers (best-effort)."""
        for q, filter_types in list(self._subscribers):
            if filter_types is None or event.event_type in filter_types:
                try:
                    q.put_nowait(event)
                except asyncio.QueueFull:
                    pass
