"""Relay hub — pull-based mailboxes so NAT-bound nodes reach each other.

A node behind home WiFi has no public address, so a peer (or the HF Space) cannot
open an inbound HTTP connection to it. The relay hub solves this with a classic
*store-and-poll* mailbox model that any node can reach outbound:

* a node **joins** the hub (``join``) → the hub creates a mailbox for it and
  returns the current roster (so the joiner learns the other members);
* to reach node *X*, a sender **enqueues** an envelope addressed to *X*
  (``send``) → it lands in *X*'s mailbox;
* *X* long-**polls** its mailbox (``poll``) → receives queued envelopes.

The hub never interprets envelope *contents* — it only routes by the ``to`` field
and gossips roster changes. RPC semantics (request/response correlation) live in
:class:`~hearthnet.transport.relay_client.RelayClient`.

The hub is framework-agnostic; :func:`mount_relay_endpoints` exposes it as FastAPI
routes (used on the Space). It can also be driven directly in tests.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Default time a member may be silent before its mailbox is pruned.
RELAY_MEMBER_TTL_SECONDS = 120
# Max envelopes held per mailbox before the oldest are dropped (back-pressure).
RELAY_MAILBOX_MAXLEN = 256


@dataclass
class _Member:
    node_id: str
    display_name: str
    community_id: str
    capabilities: list[str] = field(default_factory=list)
    endpoint: str | None = None
    joined_at: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.monotonic)
    mailbox: list[dict[str, Any]] = field(default_factory=list)
    waiter: asyncio.Event = field(default_factory=asyncio.Event)

    def view(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "display_name": self.display_name,
            "community_id": self.community_id,
            "capabilities": list(self.capabilities),
            "endpoint": self.endpoint,
            "joined_at": self.joined_at,
        }


class RelayHub:
    """Pull-based mailbox router for a community of NAT-bound nodes.

    Membership is persisted to SQLite (when *db_path* is given) so the roster
    survives process restarts — critical for HF Spaces that are restarted by the
    platform. Nodes that haven't polled within *member_ttl_seconds* are pruned from
    both the in-memory dict and the database.
    """

    def __init__(
        self,
        *,
        member_ttl_seconds: int = RELAY_MEMBER_TTL_SECONDS,
        mailbox_maxlen: int = RELAY_MAILBOX_MAXLEN,
        db_path: Path | str | None = None,
    ) -> None:
        self._members: dict[str, _Member] = {}
        self._ttl = member_ttl_seconds
        self._maxlen = mailbox_maxlen
        self._local_node_id: str | None = None
        self._local_bus: Any = None

        # SQLite persistence — optional; falls back to in-memory if unavailable.
        self._db: sqlite3.Connection | None = None
        if db_path is not None:
            with contextlib.suppress(Exception):
                db = sqlite3.connect(str(db_path), check_same_thread=False)
                db.execute(
                    """CREATE TABLE IF NOT EXISTS relay_members (
                        node_id      TEXT PRIMARY KEY,
                        display_name TEXT,
                        community_id TEXT,
                        capabilities TEXT,   -- JSON array
                        endpoint     TEXT,
                        joined_at    REAL,
                        last_seen    REAL
                    )"""
                )
                db.commit()
                self._db = db
                self._restore_members()

    # ------------------------------------------------------------------
    # SQLite helpers
    # ------------------------------------------------------------------
    def _persist_member(self, m: _Member) -> None:
        if self._db is None:
            return
        with contextlib.suppress(Exception):
            self._db.execute(
                """INSERT INTO relay_members
                       (node_id, display_name, community_id, capabilities, endpoint,
                        joined_at, last_seen)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(node_id) DO UPDATE SET
                       display_name=excluded.display_name,
                       community_id=excluded.community_id,
                       capabilities=excluded.capabilities,
                       endpoint=excluded.endpoint,
                       last_seen=excluded.last_seen""",
                (
                    m.node_id,
                    m.display_name,
                    m.community_id,
                    json.dumps(m.capabilities),
                    m.endpoint,
                    m.joined_at,
                    time.time(),
                ),
            )
            self._db.commit()

    def _remove_member_db(self, node_id: str) -> None:
        if self._db is None:
            return
        with contextlib.suppress(Exception):
            self._db.execute("DELETE FROM relay_members WHERE node_id = ?", (node_id,))
            self._db.commit()

    def _restore_members(self) -> None:
        """Load persisted members from SQLite on startup (skip stale entries)."""
        if self._db is None:
            return
        now_wall = time.time()
        cutoff = now_wall - self._ttl
        with contextlib.suppress(Exception):
            rows = self._db.execute(
                "SELECT node_id, display_name, community_id, capabilities, endpoint, "
                "joined_at, last_seen FROM relay_members WHERE last_seen > ?",
                (cutoff,),
            ).fetchall()
            for row in rows:
                node_id, display_name, community_id, caps_json, endpoint, joined_at, _ = row
                caps = json.loads(caps_json or "[]")
                member = _Member(
                    node_id=node_id,
                    display_name=display_name or node_id[:20],
                    community_id=community_id or "",
                    capabilities=caps,
                    endpoint=endpoint,
                    joined_at=joined_at or time.time(),
                )
                self._members[node_id] = member

    def set_local_handler(self, node_id: str, bus: Any) -> None:
        """Serve requests addressed to *node_id* directly via *bus* (in-process)."""
        self._local_node_id = node_id
        self._local_bus = bus

    # ------------------------------------------------------------------
    # Membership
    # ------------------------------------------------------------------
    def join(
        self,
        node_id: str,
        *,
        display_name: str = "",
        community_id: str = "",
        capabilities: list[str] | None = None,
        endpoint: str | None = None,
    ) -> dict[str, Any]:
        """Register (or refresh) a member and return the current roster.

        Existing members are notified of the newcomer via a ``roster`` envelope so
        the mesh becomes all-to-all without any node needing inbound reachability.
        """
        self.prune()
        existing = self._members.get(node_id)
        if existing is None:
            member = _Member(
                node_id=node_id,
                display_name=display_name or node_id[:20],
                community_id=community_id,
                capabilities=list(capabilities or []),
                endpoint=endpoint,
            )
            self._members[node_id] = member
            self._gossip_roster(exclude=node_id)
        else:
            existing.display_name = display_name or existing.display_name
            existing.capabilities = list(capabilities or existing.capabilities)
            existing.endpoint = endpoint or existing.endpoint
            existing.last_seen = time.monotonic()
            member = existing

        self._persist_member(member)
        return {
            "node_id": node_id,
            "roster": [m.view() for m in self._members.values() if m.node_id != node_id],
            "ttl_seconds": self._ttl,
            # The hub's own in-process node (the Space). A client can reach this
            # node directly over HTTP at the relay base URL via /bus/v1/call,
            # bypassing the mailbox poll loop entirely.
            "hub_node_id": self._local_node_id,
        }

    def leave(self, node_id: str) -> None:
        if self._members.pop(node_id, None) is not None:
            self._remove_member_db(node_id)
            self._gossip_roster()

    def roster(self) -> list[dict[str, Any]]:
        self.prune()
        return [m.view() for m in self._members.values()]

    # ------------------------------------------------------------------
    # Message routing
    # ------------------------------------------------------------------
    def send(self, to: str, envelope: dict[str, Any]) -> dict[str, Any]:
        """Enqueue *envelope* into the mailbox of node *to*.

        Returns ``{"queued": True}`` on success, or an ``error`` when the
        addressee is not a current member (unknown / expired).
        """
        member = self._members.get(to)
        if member is None:
            return {"error": "unknown_recipient", "message": f"{to} is not a relay member"}
        # In-process fast path: serve the Space's own node directly via its bus.
        if (
            to == self._local_node_id
            and self._local_bus is not None
            and envelope.get("kind") == "request"
        ):
            with contextlib.suppress(RuntimeError):
                asyncio.get_running_loop().create_task(self._serve_local(envelope))
            return {"queued": True}
        if len(member.mailbox) >= self._maxlen:
            member.mailbox.pop(0)  # drop oldest (back-pressure)
        member.mailbox.append(dict(envelope))
        member.waiter.set()
        return {"queued": True}

    async def _serve_local(self, envelope: dict[str, Any]) -> None:
        """Dispatch a request envelope to the in-process bus and mailbox the reply."""
        from hearthnet.bus import BusError
        from hearthnet.bus.capability import RouteRequest

        from_node = envelope.get("from", "")
        correlation_id = envelope.get("correlation_id", "")
        version = str(envelope.get("version", "1.0"))
        try:
            major, _, minor = version.partition(".")
            version_req = (int(major or 1), int(minor or 0))
        except ValueError:
            version_req = (1, 0)
        req = RouteRequest(
            capability=envelope.get("capability", ""),
            version_req=version_req,
            body=envelope.get("body", {}),
            caller=from_node,
            trace_id=correlation_id or "relay",
        )
        response: dict[str, Any] = {
            "kind": "response",
            "from": self._local_node_id,
            "correlation_id": correlation_id,
        }
        try:
            response["result"] = await self._local_bus.handle_call(req, local_only=True)
        except BusError as exc:
            response["error"] = exc.code
            response["message"] = str(exc)
        except Exception as exc:  # report handler failure back to the caller
            response["error"] = "internal_error"
            response["message"] = str(exc)
        if from_node:
            self.send(from_node, response)


    async def poll(self, node_id: str, *, timeout: float = 25.0) -> dict[str, Any]:
        """Long-poll a member's mailbox; return queued envelopes (drains it).

        Blocks up to *timeout* seconds waiting for the first envelope, then
        returns everything currently queued. Refreshes the member's liveness.
        """
        member = self._members.get(node_id)
        if member is None:
            return {"error": "not_joined", "message": f"{node_id} has not joined the relay"}
        member.last_seen = time.monotonic()

        if not member.mailbox:
            member.waiter.clear()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(member.waiter.wait(), timeout=timeout)

        drained = member.mailbox
        member.mailbox = []
        member.waiter.clear()
        member.last_seen = time.monotonic()
        return {"envelopes": drained}

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _gossip_roster(self, *, exclude: str | None = None) -> None:
        roster = [m.view() for m in self._members.values()]
        for member in self._members.values():
            if member.node_id == exclude:
                continue
            envelope = {
                "kind": "roster",
                "members": [m for m in roster if m["node_id"] != member.node_id],
            }
            if len(member.mailbox) >= self._maxlen:
                member.mailbox.pop(0)
            member.mailbox.append(envelope)
            member.waiter.set()

    def prune(self) -> int:
        """Drop members whose mailbox has not been polled within the TTL."""
        now = time.monotonic()
        stale = [
            nid for nid, m in self._members.items() if now - m.last_seen > self._ttl
        ]
        for nid in stale:
            self._members.pop(nid, None)
            self._remove_member_db(nid)
        if stale:
            self._gossip_roster()
        return len(stale)


def mount_relay_endpoints(app: Any, hub: RelayHub, *, prefix: str = "/relay/v1") -> bool:
    """Mount the relay hub as FastAPI routes on *app*.

    Adds ``POST {prefix}/join``, ``POST {prefix}/send``, ``GET {prefix}/poll`` and
    ``GET {prefix}/roster``. Returns ``True`` if mounted, ``False`` if FastAPI is
    unavailable or the routes already exist. Newly added routes are moved ahead of
    any SPA catch-all (Gradio mounts one).
    """
    try:
        from fastapi import Body
        from fastapi.responses import JSONResponse
    except Exception as exc:  # pragma: no cover - fastapi is a core dep
        print(f"[hearthnet] relay endpoint mount skipped: {exc}")
        return False

    join_path = f"{prefix}/join"
    if any(getattr(r, "path", "") == join_path for r in app.routes):
        return False

    body_param = Body(...)

    @app.post(join_path)
    async def _relay_join(payload: dict = body_param):
        node_id = payload.get("node_id")
        if not node_id:
            return JSONResponse({"error": "bad_request", "message": "node_id required"}, 400)
        result = hub.join(
            node_id,
            display_name=payload.get("display_name", ""),
            community_id=payload.get("community_id", ""),
            capabilities=payload.get("capabilities") or [],
            endpoint=payload.get("endpoint"),
        )
        return JSONResponse(result)

    @app.post(f"{prefix}/send")
    async def _relay_send(payload: dict = body_param):
        to = payload.get("to")
        envelope = payload.get("envelope")
        if not to or not isinstance(envelope, dict):
            return JSONResponse({"error": "bad_request", "message": "to + envelope required"}, 400)
        return JSONResponse(hub.send(to, envelope))

    @app.get(f"{prefix}/poll")
    async def _relay_poll(node_id: str, timeout: float = 25.0):
        return JSONResponse(await hub.poll(node_id, timeout=min(max(timeout, 1.0), 50.0)))

    @app.get(f"{prefix}/roster")
    async def _relay_roster():
        return JSONResponse({"roster": hub.roster()})

    for _path in (join_path, f"{prefix}/send", f"{prefix}/poll", f"{prefix}/roster"):
        for _i in range(len(app.routes) - 1, -1, -1):
            if getattr(app.routes[_i], "path", "") == _path:
                app.routes.insert(0, app.routes.pop(_i))
                break
    return True
