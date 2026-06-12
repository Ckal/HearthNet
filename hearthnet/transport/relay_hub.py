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
import time
from dataclasses import dataclass, field
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
    """In-memory mailbox router for a community of NAT-bound nodes.

    One hub instance serves one logical mesh. Membership and mailboxes are kept in
    memory (lost on process restart) — sufficient for live meshing; durable
    store-and-forward is a later enhancement.
    """

    def __init__(
        self,
        *,
        member_ttl_seconds: int = RELAY_MEMBER_TTL_SECONDS,
        mailbox_maxlen: int = RELAY_MAILBOX_MAXLEN,
    ) -> None:
        self._members: dict[str, _Member] = {}
        self._ttl = member_ttl_seconds
        self._maxlen = mailbox_maxlen

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

        return {
            "node_id": node_id,
            "roster": [m.view() for m in self._members.values() if m.node_id != node_id],
            "ttl_seconds": self._ttl,
        }

    def leave(self, node_id: str) -> None:
        if self._members.pop(node_id, None) is not None:
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
        if len(member.mailbox) >= self._maxlen:
            member.mailbox.pop(0)  # drop oldest (back-pressure)
        member.mailbox.append(dict(envelope))
        member.waiter.set()
        return {"queued": True}

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
