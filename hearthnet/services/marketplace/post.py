from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

UTC = timezone.utc
from typing import Literal

Category = Literal["offer", "request", "info", "emergency"]


@dataclass(frozen=True)
class Location:
    lat: float
    lon: float
    label: str


@dataclass(frozen=True)
class Post:
    event_id: str
    author: str  # full node_id
    category: Category
    title: str
    body: str
    location: Location | None
    tags: list[str]
    created_at: str  # RFC 3339 UTC
    expires_at: str  # RFC 3339 UTC
    lamport: int
    client_id: str  # for idempotency

    def is_expired(self, now: datetime | None = None) -> bool:
        now = now or datetime.now(UTC)
        try:
            exp = datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))
            return now > exp
        except Exception:
            return False

    def as_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "author": self.author,
            "category": self.category,
            "title": self.title,
            "body": self.body,
            "location": (
                {"lat": self.location.lat, "lon": self.location.lon, "label": self.location.label}
                if self.location
                else None
            ),
            "tags": self.tags,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "lamport": self.lamport,
            "client_id": self.client_id,
        }
