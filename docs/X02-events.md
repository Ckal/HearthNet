# X02 — Events

**Spec version:** v1.0
**Depends on:** M01 (identity), X04 (config), X03 (observability), SQLite (stdlib)
**Depended on by:** M06 (marketplace), M10 (chat), M03 (bus indirectly), M01 (community manifest regeneration)

---

## 1. Responsibility

The community-wide append-only event log. Provides:

- Durable storage of signed events
- Lamport clock management
- Replay into materialised views
- Snapshots for fast bootstrap
- Gossip sync between peers

This module knows nothing about *what* an event means semantically (that is each consuming module's concern). It enforces only ordering, signing, and durability.

---

## 2. File layout

```
hearthnet/events/
├── __init__.py
├── log.py             # EventLog: SQLite append + read
├── lamport.py         # LamportClock
├── types.py           # Event dataclass + canonical event_type strings
├── replay.py          # Replay engine for materialised views
├── snapshot.py        # SnapshotStore: write/read signed snapshots
└── sync.py            # Gossip sync protocol (heads exchange + delta push)
```

---

## 3. Public API

### 3.1 `types.py`

```python
# hearthnet/events/types.py
from dataclasses import dataclass
from typing import Any, Literal

EventType = Literal[
    "community.created",
    "community.member.invited",
    "community.member.joined",
    "community.member.revoked",
    "community.member.promoted",
    "community.member.demoted",
    "community.policy.updated",
    "node.manifest.updated",
    "market.post.created",
    "market.post.updated",
    "market.post.expired",
    "chat.message.sent",
    "chat.message.delivered",
    "chat.message.read",
    "file.cid.advertised",
    "file.cid.unpinned",
    "rag.document.ingested",
    "federation.peer.added",      # reserved
    "federation.peer.removed",    # reserved
]

@dataclass(frozen=True)
class Event:
    schema_version: int           # always 1 in this release
    event_id:       str           # ULID
    lamport:        int
    wall_clock:     str           # RFC 3339
    community_id:   str
    author:         str           # NodeID full form
    event_type:     EventType
    data:           dict[str, Any]
    signature:      str
```

### 3.2 `lamport.py`

```python
# hearthnet/events/lamport.py
class LamportClock:
    """In-memory + persisted Lamport clock for one community.

    On every send: next = ++current
    On every receive: current = max(current, received) + 1
    Persisted to SQLite on every change (atomic update inside event insert tx).
    """

    def __init__(self, conn: sqlite3.Connection, community_id: str):
        """Loads the current value from the events table head."""

    @property
    def current(self) -> int: ...

    def tick_for_send(self) -> int:
        """Returns the next Lamport value AND persists it. Idempotent within a tx."""

    def observe(self, received_lamport: int) -> None:
        """Update on receive."""
```

### 3.3 `log.py`

```python
# hearthnet/events/log.py
class EventLog:
    """SQLite-backed append-only event log for one community."""

    def __init__(self, db_path: Path, community_id: str):
        """Open or create the DB. Creates schema if absent."""

    # -- writing --

    def append_local(self, event_type: EventType, data: dict, author_kp: KeyPair) -> Event:
        """Mint a new local event: tick Lamport, sign, persist, emit pubsub.
        Returns the persisted Event."""

    def append_received(self, event: Event) -> bool:
        """Persist an event received from a peer.
        Returns True if new, False if duplicate.
        Verifies signature and ordering; raises EventLogError on invalid."""

    # -- reading --

    def head(self) -> int:
        """Highest lamport in this community."""

    def get(self, event_id: str) -> Event | None: ...

    def replay(
        self,
        *,
        since_lamport: int = 0,
        event_types: list[EventType] | None = None,
        limit: int | None = None,
    ) -> Iterator[Event]:
        """Yield events in (lamport, event_id) order."""

    def heads_by_type(self) -> dict[EventType, int]:
        """Highest lamport per event_type. Used by sync."""

    # -- pubsub fanout (in-process subscribers only) --

    def subscribe(self, event_types: list[EventType] | None = None) -> AsyncIterator[Event]: ...

class EventLogError(Exception):
    """code in {'invalid_signature','out_of_order','unknown_author','revoked_author','schema_unknown','db_corrupt'}"""
    code: str
```

### 3.4 `replay.py`

```python
# hearthnet/events/replay.py
class MaterialisedView(Protocol):
    """Each consuming module implements this to derive its state from the event stream."""
    def reset(self) -> None: ...
    def apply(self, event: Event) -> None: ...
    def snapshot_state(self) -> dict: ...
    def restore_state(self, state: dict) -> None: ...

class ReplayEngine:
    def __init__(self, log: EventLog):
        self.log = log
        self.views: dict[str, MaterialisedView] = {}

    def register(self, name: str, view: MaterialisedView, event_types: list[EventType]) -> None:
        """Register a view for replay."""

    def rebuild(self, view_name: str, from_lamport: int = 0) -> None:
        """Reset view, replay all relevant events from `from_lamport`."""

    def rebuild_all(self) -> None: ...

    def on_event(self, event: Event) -> None:
        """Apply a single new event to all subscribed views. Called by EventLog.append_*."""
```

### 3.5 `snapshot.py`

```python
# hearthnet/events/snapshot.py
@dataclass(frozen=True)
class Snapshot:
    schema_version:  int
    community_id:    str
    lamport:         int
    wall_clock:      str
    state:           dict          # union of all view snapshot_state() results
    covers_events_up_to: int
    signature:       str

class SnapshotStore:
    def __init__(self, dir_path: Path, community_id: str):
        """<DATA>/communities/<id>/snapshots/"""

    def latest(self) -> Snapshot | None: ...

    def write(self, snap: Snapshot) -> None:
        """Write atomically; filename = `<lamport>.bin`."""

    def list(self) -> list[int]:
        """Lamports of all snapshots on disk, ascending."""

    def prune(self, keep_last_n: int = 7) -> None: ...

def build_snapshot(
    log: EventLog,
    engine: ReplayEngine,
    signing_kp: KeyPair,
    at_lamport: int | None = None,
) -> Snapshot:
    """Walk views, collect snapshot_state(), sign. If at_lamport is None,
       use head - SNAPSHOT_LAG_LAMPORT."""

def restore_from_snapshot(snap: Snapshot, engine: ReplayEngine, log: EventLog) -> None:
    """Verify signature; for each view, call restore_state(); then replay events
       from snap.covers_events_up_to+1 forward to log.head()."""
```

### 3.6 `sync.py`

```python
# hearthnet/events/sync.py
@dataclass(frozen=True)
class HeadsReport:
    community_id:  str
    heads_by_type: dict[EventType, int]
    head:          int

class SyncClient:
    """Initiated by one node against a peer."""
    def __init__(self, log: EventLog, transport_client: HttpClient):
        ...

    async def sync_with(self, peer_endpoint: Endpoint) -> SyncResult:
        """1) GET /sync/v1/heads → HeadsReport
        2) compute missing → POST /sync/v1/events with our missing
        3) receive their missing
        4) apply, returns counts"""

class SyncServer:
    """Bound to the bus transport; exposes /sync/v1/heads and /sync/v1/events."""
    def __init__(self, log: EventLog):
        ...
    async def serve_heads(self) -> HeadsReport: ...
    async def serve_events(self, events: list[Event]) -> dict: ...

@dataclass(frozen=True)
class SyncResult:
    sent_count:     int
    received_count: int
    duration_ms:    int
```

---

## 4. SQLite schema

```sql
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;

CREATE TABLE IF NOT EXISTS events (
  event_id        TEXT PRIMARY KEY,           -- ULID
  community_id    TEXT NOT NULL,
  schema_version  INTEGER NOT NULL DEFAULT 1,
  lamport         INTEGER NOT NULL,
  wall_clock      TEXT NOT NULL,
  author          TEXT NOT NULL,
  event_type      TEXT NOT NULL,
  data            TEXT NOT NULL,              -- JSON
  signature       TEXT NOT NULL,
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
```

The clock row is updated inside the same transaction as the event insert for atomicity.

---

## 5. Behaviour

### 5.1 Insert flow (local event)

```
begin tx
  lamport = clock + 1
  event_id = ulid()
  build envelope { ... }
  sign with author_kp
  insert into events
  update clock
commit
fan out to in-process subscribers
fan out to remote pubsub subscribers (best-effort)
emit log line + metrics
```

### 5.2 Insert flow (received event)

```
parse + dataclass validate
verify signature (M01)
check author is a current member (read community manifest)
check event_type ∈ EventType
if duplicate event_id: return False (no-op)
begin tx
  clock = max(clock, event.lamport) + 1
  insert
  do NOT bump clock again for this transaction
commit
trigger replay engine
emit log + metrics
return True
```

### 5.3 Replay correctness

- All views must be commutative under (lamport, event_id) ordering
- The view contract is: starting from `reset()`, applying the full ordered event stream produces the same `snapshot_state()` regardless of insertion order at the log layer
- Tests assert this with property-based testing (hypothesis)

### 5.4 Snapshots

- Auto-built once per day at 03:00 local (configurable; off-peak)
- Lamport at which snapshot covers: `head - SNAPSHOT_LAG_LAMPORT` (default 1000)
- Older events not deleted unless `EVENT_LOG_RETENTION_DAYS` is exceeded (default 30 days, post-snapshot)

### 5.5 Sync rules

- Sync runs every 5 minutes (or on demand)
- During emergency mode, sync runs every 30 seconds with other local nodes only
- Sync is symmetric and idempotent — running twice causes no double-applies

---

## 6. Gossip sync protocol (wire)

### `GET /sync/v1/heads`

Response:

```json
{
  "community_id": "ed25519:...",
  "head": 4218,
  "heads_by_type": {
    "market.post.created": 4218,
    "chat.message.sent": 4192,
    "...": 0
  }
}
```

### `POST /sync/v1/events`

Body:

```json
{
  "community_id": "ed25519:...",
  "events": [ /* full Event objects */ ]
}
```

Response:

```json
{
  "accepted": 17,
  "rejected": 1,
  "rejected_reasons": [{"event_id": "...", "reason": "invalid_signature"}],
  "new_head": 4235
}
```

---

## 7. Errors

`EventLogError` codes:

- `invalid_signature` — signature did not validate
- `out_of_order` — lamport ≤ current AND event_id not novel (very rare; manifests as duplicate)
- `unknown_author` — author NodeID not in current member list
- `revoked_author` — author in revoked list at or before the event's lamport
- `schema_unknown` — `event_type` not in the closed set
- `db_corrupt` — SQLite integrity check failed

---

## 8. Configuration

From [X04](X04-config.md):

```python
config.community.state_dir   # <DATA>/communities/<id>
```

Plus constants from [GLOSSARY.md](../GLOSSARY.md):
`EVENT_LOG_RETENTION_DAYS`, `SNAPSHOT_LAG_LAMPORT`.

---

## 9. Tests

### Unit
- `test_lamport_send_increments`
- `test_lamport_observe_caps_above`
- `test_append_local_persists_and_signs`
- `test_append_received_rejects_bad_signature`
- `test_replay_idempotent` — replay twice → same state
- `test_replay_order_independence` — Hypothesis-driven, shuffle event arrival order → same end state
- `test_snapshot_roundtrip` — build, write, read, restore → equal state
- `test_duplicate_event_id_is_noop`

### Integration
- `test_two_node_sync_converges` — drift one node, sync, both equal
- `test_three_way_partition_then_heal` — three nodes, partition into 1+2, partial sync, heal, all equal
- `test_snapshot_assisted_join` — new node bootstraps from snapshot + recent events faster than full replay

---

## 10. Cross-references

| What | Where |
|------|-------|
| Event envelope | [CONTRACT §7.1](../CAPABILITY_CONTRACT.md) |
| Event types catalogue | [CONTRACT §7.2](../CAPABILITY_CONTRACT.md) |
| Lamport rules | [CONTRACT §7.3](../CAPABILITY_CONTRACT.md) |
| Sync protocol on wire | [CONTRACT §7.6](../CAPABILITY_CONTRACT.md) |
| Marketplace view | [M06 §4](../modules/M06-marketplace.md) |
| Chat view | [M10 §4](../modules/M10-chat.md) |
| Community manifest derivation | [M01 §3.2](../modules/M01-identity.md) |
| Signing | [M01 §3.1](../modules/M01-identity.md) |
