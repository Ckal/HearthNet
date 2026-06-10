from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from hearthnet.bus.capability import CapabilityDescriptor, CapabilityEntry, Handler, ParamsPredicate
from hearthnet.discovery.peers import PeerRecord
from hearthnet.types import CapabilityName, Version


@dataclass(frozen=True)
class Diff:
    added: list[CapabilityEntry]
    removed: list[CapabilityEntry]
    updated: list[CapabilityEntry]


class Registry:
    def __init__(self, our_node_id: str) -> None:
        self.our_node_id = our_node_id
        self._entries: dict[tuple[str, CapabilityName, Version], CapabilityEntry] = {}

    def register_local(
        self,
        descriptor: CapabilityDescriptor,
        handler: Handler,
        params_compatible: ParamsPredicate | None = None,
    ) -> None:
        self._entries[(self.our_node_id, descriptor.name, descriptor.version)] = CapabilityEntry(
            node_id=self.our_node_id,
            descriptor=descriptor,
            is_local=True,
            handler=handler,
            params_compatible=params_compatible or (lambda offered, requested: True),
        )

    def deregister_local(self, name: CapabilityName, version: Version) -> CapabilityEntry | None:
        return self._entries.pop((self.our_node_id, name, version), None)

    def add_remote(self, peer: PeerRecord, descriptor: CapabilityDescriptor) -> CapabilityEntry:
        endpoint = peer.endpoints[0] if peer.endpoints else None
        entry = CapabilityEntry(
            node_id=peer.node_id_full,
            descriptor=descriptor,
            is_local=False,
            endpoint=endpoint,
            last_seen=peer.last_seen,
        )
        self._entries[(peer.node_id_full, descriptor.name, descriptor.version)] = entry
        return entry

    def update_from_peer_manifest(self, peer: PeerRecord, manifest: dict[str, Any]) -> Diff:
        before = [
            entry
            for entry in self.all()
            if entry.node_id == peer.node_id_full and not entry.is_local
        ]
        for entry in before:
            self._entries.pop(
                (entry.node_id, entry.descriptor.name, entry.descriptor.version), None
            )
        added: list[CapabilityEntry] = []
        for raw in manifest.get("capabilities", []):
            descriptor = CapabilityDescriptor(
                name=raw["name"],
                version=_parse_version(raw.get("version", "1.0")),
                stability=raw.get("stability", "stable"),
                params=dict(raw.get("params", {})),
                max_concurrent=int(raw.get("max_concurrent", 1)),
            )
            added.append(self.add_remote(peer, descriptor))
        return Diff(added=added, removed=before, updated=[])

    def remove_peer(self, node_id: str) -> int:
        keys = [
            key
            for key, entry in self._entries.items()
            if entry.node_id == node_id and not entry.is_local
        ]
        for key in keys:
            self._entries.pop(key, None)
        return len(keys)

    def find(self, name: CapabilityName, version_req: Version) -> list[CapabilityEntry]:
        return [
            entry
            for entry in self._entries.values()
            if entry.descriptor.name == name and _compatible(entry.descriptor.version, version_req)
        ]

    def all_local(self) -> list[CapabilityEntry]:
        return [entry for entry in self._entries.values() if entry.is_local]

    def all_remote(self) -> list[CapabilityEntry]:
        return [entry for entry in self._entries.values() if not entry.is_local]

    def all(self) -> list[CapabilityEntry]:
        return list(self._entries.values())


def _compatible(offered: Version, requested: Version) -> bool:
    return offered[0] == requested[0] and offered[1] >= requested[1]


def _parse_version(raw: str) -> Version:
    major, minor = raw.split(".", 1)
    return int(major), int(minor)
