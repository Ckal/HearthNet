from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .types import Event

if TYPE_CHECKING:
    from .log import EventLog


@dataclass(frozen=True)
class HeadsReport:
    community_id: str
    node_id: str
    head: int
    heads_by_type: dict[str, int]


@dataclass(frozen=True)
class SyncResult:
    sent_count: int
    received_count: int
    duration_ms: int


def _event_to_dict(event: Event) -> dict[str, Any]:
    return {
        "schema_version": event.schema_version,
        "event_id": event.event_id,
        "event_type": event.event_type,
        "community_id": event.community_id,
        "author": event.author,
        "lamport": event.lamport,
        "payload": event.payload,
        "issued_at": event.issued_at,
        "signature": event.signature,
    }


def _dict_to_event(d: dict[str, Any]) -> Event:
    return Event(
        schema_version=d.get("schema_version", 1),
        event_id=d["event_id"],
        event_type=d["event_type"],
        community_id=d["community_id"],
        author=d["author"],
        lamport=d["lamport"],
        payload=d.get("payload", {}),
        issued_at=d["issued_at"],
        signature=d.get("signature", ""),
    )


class SyncClient:
    """Pull/push gossip sync against a single peer."""

    def __init__(self, log: EventLog, http_client: Any = None) -> None:
        self._log = log
        self._http = http_client

    async def sync_with(self, peer_url: str, community_id: str) -> SyncResult:
        """Gossip sync with peer:
        1. GET /sync/v1/heads   → peer HeadsReport
        2. POST /sync/v1/events → push events peer is missing
        3. Receive events we are missing and apply them.
        """
        start = int(time.time() * 1000)

        if self._http is None:
            # No transport available; return a no-op result
            return SyncResult(sent_count=0, received_count=0, duration_ms=0)

        # Step 1: fetch peer heads
        resp = await self._http.get(f"{peer_url.rstrip('/')}/sync/v1/heads")
        peer_heads: dict[str, Any] = resp if isinstance(resp, dict) else await resp.json()
        peer_head: int = peer_heads.get("head", 0)

        # Step 2: send events peer doesn't have
        local_head = self._log.head()
        our_missing: list[dict[str, Any]] = []
        if local_head > peer_head:
            events_to_send = self._log.since(peer_head + 1)
            our_missing = [_event_to_dict(e) for e in events_to_send]

        # Step 3: POST our missing and receive theirs
        body = json.dumps(
            {
                "community_id": community_id,
                "events": our_missing,
                "our_head": local_head,
            }
        )
        resp2 = await self._http.post(
            f"{peer_url.rstrip('/')}/sync/v1/events",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        result_data: dict[str, Any] = resp2 if isinstance(resp2, dict) else await resp2.json()

        # Apply events the peer sent back
        received_events: list[dict[str, Any]] = result_data.get("events", [])
        received_count = 0
        for ed in received_events:
            try:
                event = _dict_to_event(ed)
                if self._log.append_received(event):
                    received_count += 1
            except Exception:
                pass

        duration_ms = int(time.time() * 1000) - start
        return SyncResult(
            sent_count=len(our_missing),
            received_count=received_count,
            duration_ms=duration_ms,
        )


class SyncServer:
    """Exposes /sync/v1/heads and /sync/v1/events handler logic."""

    def __init__(self, log: EventLog) -> None:
        self._log = log

    def heads(self) -> HeadsReport:
        return HeadsReport(
            community_id=self._log._community_id,
            node_id="",  # caller should inject node_id if needed
            head=self._log.head(),
            heads_by_type=self._log.heads_by_type(),
        )

    async def serve_heads(self) -> dict[str, Any]:
        report = self.heads()
        return {
            "community_id": report.community_id,
            "head": report.head,
            "heads_by_type": report.heads_by_type,
        }

    async def serve_events(self, body: dict[str, Any]) -> dict[str, Any]:
        """Accept events from a peer and return events the peer is missing.

        Expected body keys: ``community_id``, ``events``, ``our_head`` (peer's head).
        """
        incoming: list[dict[str, Any]] = body.get("events", [])
        peer_head: int = body.get("our_head", 0)

        accepted = 0
        rejected = 0
        rejected_reasons: list[dict[str, str]] = []

        for ed in incoming:
            try:
                event = _dict_to_event(ed)
                if self._log.append_received(event):
                    accepted += 1
            except Exception as exc:
                rejected += 1
                rejected_reasons.append(
                    {
                        "event_id": ed.get("event_id", ""),
                        "reason": str(exc),
                    }
                )

        # Events the requesting peer is missing
        missing_for_peer = [_event_to_dict(e) for e in self._log.since(peer_head + 1)]

        return {
            "accepted": accepted,
            "rejected": rejected,
            "rejected_reasons": rejected_reasons,
            "new_head": self._log.head(),
            "events": missing_for_peer,
        }
