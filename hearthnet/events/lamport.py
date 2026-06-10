from __future__ import annotations

import sqlite3
import threading
from pathlib import Path


class LamportClock:
    """Thread-safe, SQLite-persisted Lamport clock for one community.

    The clock row lives in the same ``clock`` table as the event log DB so
    that both the event insert and the clock bump happen in the same
    transaction.
    """

    def __init__(self, community_id: str, db_path: Path) -> None:
        self._community_id = community_id
        self._db_path = db_path
        self._lock = threading.Lock()
        self._value: int = 0
        self._conn: sqlite3.Connection | None = None
        self._load()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def tick(self) -> int:
        """Increment and return the new Lamport value (for local events)."""
        with self._lock:
            self._value += 1
            self._save()
            return self._value

    def update(self, received: int) -> int:
        """Advance to max(local, received) + 1 (for received events)."""
        with self._lock:
            self._value = max(self._value, received) + 1
            self._save()
            return self._value

    def current(self) -> int:
        with self._lock:
            return self._value

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        return self._conn

    def _load(self) -> None:
        conn = self._get_conn()
        conn.execute(
            "CREATE TABLE IF NOT EXISTS clock "
            "(community_id TEXT PRIMARY KEY, lamport INTEGER NOT NULL)"
        )
        conn.commit()
        row = conn.execute(
            "SELECT lamport FROM clock WHERE community_id = ?",
            (self._community_id,),
        ).fetchone()
        self._value = row[0] if row else 0

    def _save(self) -> None:
        """Persist current value.  Called while ``_lock`` is held."""
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO clock (community_id, lamport) VALUES (?, ?) "
            "ON CONFLICT(community_id) DO UPDATE SET lamport = excluded.lamport",
            (self._community_id, self._value),
        )
        conn.commit()

    def _save_in_tx(self, conn: sqlite3.Connection) -> None:
        """Persist inside an already-open transaction (no commit here)."""
        conn.execute(
            "INSERT INTO clock (community_id, lamport) VALUES (?, ?) "
            "ON CONFLICT(community_id) DO UPDATE SET lamport = excluded.lamport",
            (self._community_id, self._value),
        )
