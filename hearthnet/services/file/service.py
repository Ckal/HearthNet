from __future__ import annotations

import base64
from typing import Any

from hearthnet.blobs.store import BlobStore
from hearthnet.bus.capability import CapabilityDescriptor, RouteRequest


class FileService:
    name = "file"
    version = "1.0"

    def __init__(self, store: BlobStore) -> None:
        self.store = store

    def capabilities(self) -> list[tuple[Any, ...]]:
        return [
            (
                CapabilityDescriptor(
                    name="file.read",
                    params={},
                    trust_required="member",
                    max_concurrent=8,
                ),
                self.handle_read,
                None,
            ),
            (
                CapabilityDescriptor(
                    name="file.list",
                    params={},
                    trust_required="member",
                    max_concurrent=8,
                ),
                self.handle_list,
                None,
            ),
            (
                CapabilityDescriptor(
                    name="file.advertise",
                    params={},
                    trust_required="member",
                    max_concurrent=4,
                ),
                self.handle_advertise,
                None,
            ),
            (
                CapabilityDescriptor(
                    name="file.put",
                    params={},
                    trust_required="trusted",
                    max_concurrent=2,
                    timeout_seconds=600,
                ),
                self.handle_put,
                None,
            ),
        ]

    async def handle_read(self, req: RouteRequest) -> dict[str, Any]:
        """input: {cid: str} → output: {cid, size_bytes, filename, chunks: [...]}"""
        cid = req.body.get("input", {}).get("cid", "")
        if not self.store.has(cid):
            return {"error": "not_found", "message": f"Blob {cid} not found"}
        manifest = self.store.get_manifest(cid)
        return {
            "output": {
                "cid": manifest.cid,
                "size_bytes": manifest.size_bytes,
                "filename": manifest.filename,
                "chunks": [
                    {"index": c.index, "cid": c.cid, "size_bytes": c.size_bytes}
                    for c in manifest.chunks
                ],
            },
            "meta": {},
        }

    async def handle_list(self, req: RouteRequest) -> dict[str, Any]:
        blobs = self.store.list_blobs()
        return {
            "output": {
                "blobs": [
                    {"cid": b.cid, "size_bytes": b.size_bytes, "filename": b.filename}
                    for b in blobs
                ]
            },
            "meta": {},
        }

    async def handle_advertise(self, req: RouteRequest) -> dict[str, Any]:
        """input: {cid, filename, size_bytes} → acknowledge, actual transfer is separate"""
        inp = req.body.get("input", {})
        return {"output": {"acknowledged": True, "cid": inp.get("cid")}, "meta": {}}

    async def handle_put(self, req: RouteRequest) -> dict[str, Any]:
        """input: {data_b64: str, filename: str} → store blob → output: {cid, size_bytes}"""
        inp = req.body.get("input", {})
        data_b64 = inp.get("data_b64", "")
        filename = inp.get("filename")
        try:
            data = base64.b64decode(data_b64)
        except Exception:
            return {"error": "bad_request", "message": "Invalid base64 data"}
        manifest = self.store.put(data, filename=filename)
        return {"output": {"cid": manifest.cid, "size_bytes": manifest.size_bytes}, "meta": {}}
