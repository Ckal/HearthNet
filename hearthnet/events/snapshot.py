from __future__ import annotations

import base64
import contextlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .log import EventLog
    from .replay import ReplayEngine

_SNAPSHOT_LAG_LAMPORT = 1000
_SCHEMA_VERSION = 1


def _now_utc() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def _sign_snapshot(data: bytes, kp: Any) -> str:
    if kp is None:
        return ""
    if hasattr(kp, "sign"):
        sig_bytes: bytes = kp.sign(data)
    else:
        import hashlib
        import hmac

        sig_bytes = hmac.new(kp, data, hashlib.sha256).digest()
    return "ed25519:" + base64.urlsafe_b64encode(sig_bytes).rstrip(b"=").decode()


def _verify_snapshot(snap: Snapshot, kp_store: Any) -> bool:
    if kp_store is None or not snap.signature:
        return True
    raw = _canonical_snap_bytes(snap)
    if hasattr(kp_store, "verify"):
        try:
            prefix = "ed25519:"
            b64 = (
                snap.signature[len(prefix) :]
                if snap.signature.startswith(prefix)
                else snap.signature
            )
            padding = 4 - len(b64) % 4
            if padding != 4:
                b64 += "=" * padding
            sig_bytes = base64.urlsafe_b64decode(b64)
            return kp_store.verify(snap.author, raw, sig_bytes)
        except Exception:
            return False
    return True


def _canonical_snap_bytes(snap: Snapshot) -> bytes:
    obj = {
        "schema_version": snap.schema_version,
        "community_id": snap.community_id,
        "at_lamport": snap.at_lamport,
        "views": snap.views,
        "issued_at": snap.issued_at,
        "author": snap.author,
    }
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


@dataclass(frozen=True)
class Snapshot:
    schema_version: int
    community_id: str
    at_lamport: int
    views: dict[str, dict]  # view_name -> state dict
    issued_at: str
    author: str
    signature: str


class SnapshotStore:
    """Stores snapshots as JSON files under *dir_path*/<community_id>/snapshots/."""

    def __init__(self, dir_path: Path, community_id: str) -> None:
        self._dir = dir_path / community_id / "snapshots"
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path_for(self, at_lamport: int) -> Path:
        return self._dir / f"{at_lamport:020d}.json"

    def write(self, snap: Snapshot) -> None:
        """Write snapshot atomically."""
        target = self._path_for(snap.at_lamport)
        tmp = target.with_suffix(".tmp")
        payload = {
            "schema_version": snap.schema_version,
            "community_id": snap.community_id,
            "at_lamport": snap.at_lamport,
            "views": snap.views,
            "issued_at": snap.issued_at,
            "author": snap.author,
            "signature": snap.signature,
        }
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(tmp, target)

    def latest(self) -> Snapshot | None:
        lamps = self.list()
        if not lamps:
            return None
        return self._load(lamps[-1])

    def list(self) -> list[int]:
        """Return lamport values of all snapshots on disk, ascending."""
        values = []
        for p in sorted(self._dir.glob("*.json")):
            with contextlib.suppress(ValueError):
                values.append(int(p.stem))
        return values

    def prune(self, keep_last_n: int = 7) -> None:
        lamps = self.list()
        to_delete = lamps[:-keep_last_n] if len(lamps) > keep_last_n else []
        for lamp in to_delete:
            self._path_for(lamp).unlink(missing_ok=True)

    def _load(self, at_lamport: int) -> Snapshot:
        data = json.loads(self._path_for(at_lamport).read_text(encoding="utf-8"))
        return Snapshot(
            schema_version=data["schema_version"],
            community_id=data["community_id"],
            at_lamport=data["at_lamport"],
            views=data["views"],
            issued_at=data["issued_at"],
            author=data["author"],
            signature=data["signature"],
        )


def build_snapshot(
    log: EventLog,
    engine: ReplayEngine,
    author: str,
    kp: Any = None,
    at_lamport: int | None = None,
) -> Snapshot:
    """Build a signed snapshot of all view states up to *at_lamport*.

    If *at_lamport* is None, uses ``head - SNAPSHOT_LAG_LAMPORT``.
    """
    head = log.head()
    if at_lamport is None:
        at_lamport = max(0, head - _SNAPSHOT_LAG_LAMPORT)

    # Rebuild all views up to at_lamport
    for (view, ft) in engine._views.values():
        view.reset()
        event_types = list(ft) if ft is not None else None
        for event in log.replay(since_lamport=0, event_types=event_types):  # type: ignore[arg-type]
            if event.lamport > at_lamport:
                break
            view.apply(event)
            if event.lamport > at_lamport:
                break
            view.apply(event)

    views_state: dict[str, dict] = {}
    for name, (view, _ft) in engine._views.items():
        views_state[name] = view.snapshot_state()

    now = _now_utc()
    snap_unsigned = Snapshot(
        schema_version=_SCHEMA_VERSION,
        community_id=log._community_id,
        at_lamport=at_lamport,
        views=views_state,
        issued_at=now,
        author=author,
        signature="",
    )
    sig = _sign_snapshot(_canonical_snap_bytes(snap_unsigned), kp)
    import dataclasses

    return dataclasses.replace(snap_unsigned, signature=sig)


def restore_from_snapshot(
    snap: Snapshot,
    engine: ReplayEngine,
    log: EventLog,
    kp_store: Any = None,
) -> None:
    """Restore view states from *snap*, then replay any newer events."""
    if not _verify_snapshot(snap, kp_store):
        raise ValueError("Snapshot signature verification failed")

    for name, state in snap.views.items():
        if name in engine._views:
            engine._views[name][0].restore_state(state)

    # Replay events that arrived after the snapshot
    for event in log.replay(since_lamport=snap.at_lamport + 1):
        engine._on_event(event)
