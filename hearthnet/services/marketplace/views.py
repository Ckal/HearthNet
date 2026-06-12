from __future__ import annotations

from datetime import datetime, timezone

UTC = timezone.utc

UTC = UTC
from typing import Any

from hearthnet.services.marketplace.post import Location, Post


class MarketplaceView:
    """MaterialisedView: maintains set of active (non-expired) posts from event stream."""

    def __init__(self) -> None:
        self._posts: dict[str, Post] = {}  # event_id -> Post
        self._expired: set[str] = set()  # event_ids that are expired
        self._seen_client_ids: set[str] = set()

    def apply(self, event: Any) -> None:
        """Process one event. Compatible with X02 Event dataclass or dict."""
        if hasattr(event, "event_type"):
            etype = event.event_type
            payload = event.payload
            event_id = event.event_id
            author = event.author
            lamport = event.lamport
        else:
            etype = event.get("event_type", "")
            payload = event.get("payload", {})
            event_id = event.get("event_id", "")
            author = event.get("author", "")
            lamport = event.get("lamport", 0)

        if etype == "market.post.created":
            client_id = payload.get("client_id", event_id)
            if client_id in self._seen_client_ids:
                return  # idempotent
            self._seen_client_ids.add(client_id)
            loc_raw = payload.get("location")
            location = Location(**loc_raw) if loc_raw else None
            post = Post(
                event_id=event_id,
                author=author,
                category=payload.get("category", "info"),
                title=payload.get("title", ""),
                body=payload.get("body", ""),
                location=location,
                tags=payload.get("tags", []),
                created_at=payload.get("created_at", ""),
                expires_at=payload.get("expires_at", ""),
                lamport=lamport,
                client_id=client_id,
            )
            self._posts[event_id] = post

        elif etype in ("market.post.expired", "market.post.updated"):
            target_id = payload.get("target_event_id", event_id)
            if target_id in self._posts:
                self._expired.add(target_id)

    def all_active(self) -> list[Post]:
        now = datetime.now(UTC)
        return [
            post
            for eid, post in self._posts.items()
            if eid not in self._expired and not post.is_expired(now)
        ]

    def snapshot_state(self) -> dict:
        return {
            "posts": {eid: p.as_dict() for eid, p in self._posts.items()},
            "expired": list(self._expired),
            "seen_client_ids": list(self._seen_client_ids),
        }

    def restore_state(self, state: dict) -> None:
        self._posts = {}
        for eid, pd in state.get("posts", {}).items():
            loc = Location(**pd["location"]) if pd.get("location") else None
            self._posts[eid] = Post(
                event_id=pd["event_id"],
                author=pd["author"],
                category=pd["category"],
                title=pd["title"],
                body=pd["body"],
                location=loc,
                tags=pd["tags"],
                created_at=pd["created_at"],
                expires_at=pd["expires_at"],
                lamport=pd["lamport"],
                client_id=pd["client_id"],
            )
        self._expired = set(state.get("expired", []))
        self._seen_client_ids = set(state.get("seen_client_ids", []))

    def reset(self) -> None:
        self._posts.clear()
        self._expired.clear()
        self._seen_client_ids.clear()
