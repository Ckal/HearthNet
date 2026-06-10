from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class DhtContact:
    node_key: bytes        # 32-byte SHA-256 of node_id
    endpoint: str          # "host:port"
    node_id: str           # human-readable node identifier
    last_seen: float       # monotonic timestamp


@dataclass(frozen=True)
class DhtValue:
    key: bytes             # lookup key (arbitrary bytes)
    payload: dict          # stored data
    expires_at: int        # Unix epoch seconds


def _xor_distance(a: bytes, b: bytes) -> int:
    """XOR metric over equal-length byte strings, returned as integer."""
    # Pad to same length if needed
    la, lb = len(a), len(b)
    if la < lb:
        a = a.ljust(lb, b"\x00")
    elif lb < la:
        b = b.ljust(la, b"\x00")
    result = 0
    for x, y in zip(a, b):
        result = (result << 8) | (x ^ y)
    return result


def _bucket_index(own_key: bytes, target_key: bytes) -> int:
    """Return the Kademlia bucket index [0, 255] for the target key."""
    dist = _xor_distance(own_key, target_key)
    if dist == 0:
        return 0
    # Most-significant bit position of the XOR distance
    bit_length = dist.bit_length()
    return bit_length - 1  # 0-based, max 255 for 32-byte keys


class RoutingTable:
    """256 buckets of K=8 contacts each."""

    def __init__(self, own_key: bytes, k: int = 8) -> None:
        self._own_key = own_key
        self._k = k
        self._buckets: list[list[DhtContact]] = [[] for _ in range(256)]

    def add_contact(self, contact: DhtContact) -> None:
        if contact.node_key == self._own_key:
            return
        idx = _bucket_index(self._own_key, contact.node_key)
        bucket = self._buckets[idx]

        # Replace existing entry for the same node_key
        for i, existing in enumerate(bucket):
            if existing.node_key == contact.node_key:
                bucket[i] = contact
                return

        if len(bucket) < self._k:
            bucket.append(contact)
        else:
            # Replace the oldest (least recently seen) contact
            oldest_idx = min(range(len(bucket)), key=lambda i: bucket[i].last_seen)
            bucket[oldest_idx] = contact

    def find_closest(self, key: bytes, k: int = 8) -> list[DhtContact]:
        """Return up to k contacts closest (by XOR) to key."""
        all_contacts = self.all_contacts()
        all_contacts.sort(key=lambda c: _xor_distance(c.node_key, key))
        return all_contacts[:k]

    def size(self) -> int:
        return sum(len(b) for b in self._buckets)

    def all_contacts(self) -> list[DhtContact]:
        contacts: list[DhtContact] = []
        for bucket in self._buckets:
            contacts.extend(bucket)
        return contacts


class KademliaNode:
    """Local Kademlia DHT node: routing table + local value store."""

    def __init__(self, node_id: str, k: int = 8, alpha: int = 3) -> None:
        self._node_id = node_id
        self._k = k
        self._alpha = alpha

        # Deterministic 32-byte key from node_id
        self.node_key: bytes = hashlib.sha256(node_id.encode()).digest()

        self.routing_table = RoutingTable(own_key=self.node_key, k=k)
        self.local_store: dict[bytes, DhtValue] = {}

    # ── Value store ───────────────────────────────────────────────────────────

    def store(self, key: bytes, value: dict, ttl: int = 3600) -> None:
        expires_at = int(time.time()) + ttl
        self.local_store[key] = DhtValue(key=key, payload=value, expires_at=expires_at)

    def find_value(self, key: bytes) -> DhtValue | None:
        entry = self.local_store.get(key)
        if entry is None:
            return None
        if int(time.time()) > entry.expires_at:
            del self.local_store[key]
            return None
        return entry

    # ── Routing ───────────────────────────────────────────────────────────────

    def find_closest(self, key: bytes, k: int = 8) -> list[DhtContact]:
        return self.routing_table.find_closest(key, k)

    def update_contact(self, contact: DhtContact) -> None:
        self.routing_table.add_contact(contact)

    # ── Maintenance ───────────────────────────────────────────────────────────

    def expire_stale(self) -> int:
        """Remove expired values. Returns count of removed entries."""
        now = int(time.time())
        stale = [k for k, v in self.local_store.items() if now > v.expires_at]
        for k in stale:
            del self.local_store[k]
        return len(stale)
