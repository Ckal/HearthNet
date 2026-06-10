from __future__ import annotations

import base64
import secrets
import time
from dataclasses import dataclass
from typing import Any, Literal

EventType = Literal[
    "community.created",
    "community.member.joined",
    "community.member.left",
    "community.member.invited",
    "community.member.removed",
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
    "rag.document.ingested",
    "file.advertised",
    "file.cid.advertised",
    "file.cid.unpinned",
    "federation.peer.added",
    "federation.peer.removed",
]

_ALL_EVENT_TYPES: frozenset[str] = frozenset(EventType.__args__)  # type: ignore[attr-defined]


def new_ulid() -> str:
    """Generate a sortable unique ID (ULID-compatible 26-char string)."""
    ts = int(time.time() * 1000)
    ts_bytes = ts.to_bytes(10, "big")
    rand_bytes = secrets.token_bytes(10)
    raw = ts_bytes + rand_bytes  # 20 bytes
    encoded = base64.b32encode(raw).decode("ascii")  # 32 chars
    return encoded[:26]


@dataclass(frozen=True)
class Event:
    schema_version: int  # always 1
    event_id: str  # ULID
    event_type: EventType
    community_id: str
    author: str  # full node_id
    lamport: int
    payload: dict[str, Any]
    issued_at: str  # RFC 3339 UTC
    signature: str  # "ed25519:<b64url>" or ""
