from __future__ import annotations

import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Thread:
    thread_id: str
    name: str
    members: list[str]
    created_at: float
    archived: bool
    e2e_enabled: bool


@dataclass(frozen=True)
class ThreadMessage:
    event_id: str
    thread_id: str
    sender: str
    content: str
    sent_at: float
    delivered_to: frozenset[str]


class ThreadViewStore:
    """Materialised view of thread state from chat.thread.* events.

    Uses SQLite when available, falls back to in-memory dicts.
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._lock = threading.Lock()
        self._db: sqlite3.Connection | None = None

        # In-memory fallback structures
        self._threads: dict[str, dict] = {}  # thread_id -> thread data
        self._members: dict[str, set[str]] = {}  # thread_id -> set of member_ids
        self._messages: dict[str, dict] = {}  # event_id -> message data
        self._msg_by_thread: dict[str, list[str]] = {}  # thread_id -> [event_id, ...]
        # read receipts: thread_id -> {member_id -> last_read_ts}
        self._read_receipts: dict[str, dict[str, float]] = {}

        if db_path:
            try:
                self._db = sqlite3.connect(str(db_path), check_same_thread=False)
                self._db.execute("PRAGMA journal_mode=WAL")
                self._init_schema()
            except Exception:
                self._db = None

    def _init_schema(self) -> None:
        assert self._db is not None
        self._db.executescript("""
            CREATE TABLE IF NOT EXISTS threads (
                thread_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created_at REAL NOT NULL,
                archived INTEGER NOT NULL DEFAULT 0,
                e2e_enabled INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS thread_members (
                thread_id TEXT NOT NULL,
                member_id TEXT NOT NULL,
                PRIMARY KEY (thread_id, member_id)
            );
            CREATE TABLE IF NOT EXISTS thread_messages (
                event_id TEXT PRIMARY KEY,
                thread_id TEXT NOT NULL,
                sender TEXT NOT NULL,
                content TEXT NOT NULL,
                sent_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS delivered_to (
                event_id TEXT NOT NULL,
                member_id TEXT NOT NULL,
                PRIMARY KEY (event_id, member_id)
            );
            CREATE TABLE IF NOT EXISTS read_receipts (
                thread_id TEXT NOT NULL,
                member_id TEXT NOT NULL,
                last_read_ts REAL NOT NULL,
                PRIMARY KEY (thread_id, member_id)
            );
        """)
        self._db.commit()

    # ── Apply event ───────────────────────────────────────────────────────────

    def apply(self, event: dict) -> None:
        etype = event.get("event_type", "")
        payload = event.get("payload", {})
        author = event.get("author", "")
        event_id = event.get("event_id", "")

        with self._lock:
            if etype == "chat.thread.created":
                self._apply_thread_created(event_id, payload, author)
            elif etype == "chat.thread.message.sent":
                self._apply_message_sent(event_id, payload, author)
            elif etype == "chat.thread.member.added":
                self._apply_member_added(payload)
            elif etype == "chat.thread.member.removed":
                self._apply_member_removed(payload)
            elif etype == "chat.thread.archived":
                self._apply_archived(payload)

    def _apply_thread_created(self, event_id: str, payload: dict, author: str) -> None:
        thread_id = payload.get("thread_id", event_id)
        members: list[str] = list(payload.get("members", []))
        if author and author not in members:
            members.append(author)
        name = payload.get("name", "")
        created_at = payload.get("created_at", time.time())
        e2e_enabled = bool(payload.get("e2e_enabled", False))

        if self._db:
            self._db.execute(
                "INSERT OR IGNORE INTO threads (thread_id, name, created_at, archived, e2e_enabled) VALUES (?,?,?,0,?)",
                (thread_id, name, created_at, int(e2e_enabled)),
            )
            for m in members:
                self._db.execute(
                    "INSERT OR IGNORE INTO thread_members (thread_id, member_id) VALUES (?,?)",
                    (thread_id, m),
                )
            self._db.commit()
        else:
            if thread_id not in self._threads:
                self._threads[thread_id] = {
                    "thread_id": thread_id,
                    "name": name,
                    "created_at": created_at,
                    "archived": False,
                    "e2e_enabled": e2e_enabled,
                }
                self._members[thread_id] = set(members)
                self._msg_by_thread[thread_id] = []

    def _apply_message_sent(self, event_id: str, payload: dict, author: str) -> None:
        thread_id = payload.get("thread_id", "")
        sender = payload.get("sender", author)
        content = payload.get("content", "")
        sent_at = payload.get("sent_at", time.time())

        if self._db:
            self._db.execute(
                "INSERT OR IGNORE INTO thread_messages (event_id, thread_id, sender, content, sent_at) VALUES (?,?,?,?,?)",
                (event_id, thread_id, sender, content, sent_at),
            )
            self._db.commit()
        else:
            if event_id not in self._messages:
                self._messages[event_id] = {
                    "event_id": event_id,
                    "thread_id": thread_id,
                    "sender": sender,
                    "content": content,
                    "sent_at": sent_at,
                    "delivered_to": set(),
                }
                self._msg_by_thread.setdefault(thread_id, []).append(event_id)

    def _apply_member_added(self, payload: dict) -> None:
        thread_id = payload.get("thread_id", "")
        member_id = payload.get("member_id", "")
        if not thread_id or not member_id:
            return

        if self._db:
            self._db.execute(
                "INSERT OR IGNORE INTO thread_members (thread_id, member_id) VALUES (?,?)",
                (thread_id, member_id),
            )
            self._db.commit()
        else:
            self._members.setdefault(thread_id, set()).add(member_id)

    def _apply_member_removed(self, payload: dict) -> None:
        thread_id = payload.get("thread_id", "")
        member_id = payload.get("member_id", "")
        if not thread_id or not member_id:
            return

        if self._db:
            self._db.execute(
                "DELETE FROM thread_members WHERE thread_id=? AND member_id=?",
                (thread_id, member_id),
            )
            self._db.commit()
        else:
            self._members.get(thread_id, set()).discard(member_id)

    def _apply_archived(self, payload: dict) -> None:
        thread_id = payload.get("thread_id", "")
        if not thread_id:
            return

        if self._db:
            self._db.execute("UPDATE threads SET archived=1 WHERE thread_id=?", (thread_id,))
            self._db.commit()
        else:
            if thread_id in self._threads:
                t = self._threads[thread_id]
                t["archived"] = True

    # ── Queries ───────────────────────────────────────────────────────────────

    def get_thread(self, thread_id: str) -> Thread | None:
        with self._lock:
            if self._db:
                row = self._db.execute(
                    "SELECT thread_id, name, created_at, archived, e2e_enabled FROM threads WHERE thread_id=?",
                    (thread_id,),
                ).fetchone()
                if not row:
                    return None
                members_rows = self._db.execute(
                    "SELECT member_id FROM thread_members WHERE thread_id=?", (thread_id,)
                ).fetchall()
                members = [r[0] for r in members_rows]
                return Thread(
                    thread_id=row[0],
                    name=row[1],
                    members=members,
                    created_at=row[2],
                    archived=bool(row[3]),
                    e2e_enabled=bool(row[4]),
                )
            t = self._threads.get(thread_id)
            if not t:
                return None
            return Thread(
                thread_id=t["thread_id"],
                name=t["name"],
                members=list(self._members.get(thread_id, set())),
                created_at=t["created_at"],
                archived=t["archived"],
                e2e_enabled=t["e2e_enabled"],
            )

    def list_threads(self, member_id: str) -> list[Thread]:
        with self._lock:
            if self._db:
                rows = self._db.execute(
                    """SELECT t.thread_id, t.name, t.created_at, t.archived, t.e2e_enabled
                       FROM threads t
                       JOIN thread_members tm ON t.thread_id=tm.thread_id
                       WHERE tm.member_id=?
                       ORDER BY t.created_at DESC""",
                    (member_id,),
                ).fetchall()
                result = []
                for row in rows:
                    thread_id = row[0]
                    members_rows = self._db.execute(
                        "SELECT member_id FROM thread_members WHERE thread_id=?", (thread_id,)
                    ).fetchall()
                    members = [r[0] for r in members_rows]
                    result.append(
                        Thread(
                            thread_id=thread_id,
                            name=row[1],
                            members=members,
                            created_at=row[2],
                            archived=bool(row[3]),
                            e2e_enabled=bool(row[4]),
                        )
                    )
                return result
            results = []
            for tid, members in self._members.items():
                if member_id in members:
                    t = self._threads.get(tid)
                    if t:
                        results.append(
                            Thread(
                                thread_id=t["thread_id"],
                                name=t["name"],
                                members=list(members),
                                created_at=t["created_at"],
                                archived=t["archived"],
                                e2e_enabled=t["e2e_enabled"],
                            )
                        )
            results.sort(key=lambda x: x.created_at, reverse=True)
            return results

    def get_messages(
        self,
        thread_id: str,
        since: float | None = None,
        limit: int = 50,
    ) -> list[ThreadMessage]:
        with self._lock:
            if self._db:
                if since is not None:
                    rows = self._db.execute(
                        "SELECT event_id, thread_id, sender, content, sent_at FROM thread_messages "
                        "WHERE thread_id=? AND sent_at>? ORDER BY sent_at ASC LIMIT ?",
                        (thread_id, since, limit),
                    ).fetchall()
                else:
                    rows = self._db.execute(
                        "SELECT event_id, thread_id, sender, content, sent_at FROM thread_messages "
                        "WHERE thread_id=? ORDER BY sent_at ASC LIMIT ?",
                        (thread_id, limit),
                    ).fetchall()
                messages = []
                for row in rows:
                    eid = row[0]
                    delivered_rows = self._db.execute(
                        "SELECT member_id FROM delivered_to WHERE event_id=?", (eid,)
                    ).fetchall()
                    delivered = frozenset(r[0] for r in delivered_rows)
                    messages.append(
                        ThreadMessage(
                            event_id=eid,
                            thread_id=row[1],
                            sender=row[2],
                            content=row[3],
                            sent_at=row[4],
                            delivered_to=delivered,
                        )
                    )
                return messages
            eids = self._msg_by_thread.get(thread_id, [])
            msgs = []
            for eid in eids:
                m = self._messages.get(eid)
                if m and (since is None or m["sent_at"] > since):
                    msgs.append(
                        ThreadMessage(
                            event_id=m["event_id"],
                            thread_id=m["thread_id"],
                            sender=m["sender"],
                            content=m["content"],
                            sent_at=m["sent_at"],
                            delivered_to=frozenset(m["delivered_to"]),
                        )
                    )
            msgs.sort(key=lambda x: x.sent_at)
            return msgs[:limit]

    def unread_count(self, thread_id: str, member_id: str) -> int:
        with self._lock:
            if self._db:
                row = self._db.execute(
                    "SELECT last_read_ts FROM read_receipts WHERE thread_id=? AND member_id=?",
                    (thread_id, member_id),
                ).fetchone()
                last_read = row[0] if row else 0.0
                count = self._db.execute(
                    "SELECT COUNT(*) FROM thread_messages WHERE thread_id=? AND sent_at>? AND sender!=?",
                    (thread_id, last_read, member_id),
                ).fetchone()[0]
                return int(count)
            last_read = self._read_receipts.get(thread_id, {}).get(member_id, 0.0)
            eids = self._msg_by_thread.get(thread_id, [])
            count = 0
            for eid in eids:
                m = self._messages.get(eid)
                if m and m["sent_at"] > last_read and m["sender"] != member_id:
                    count += 1
            return count
