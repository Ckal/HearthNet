"""M07 — File / Blob store service.

Provides file.put, file.get, file.list, file.delete capabilities via the bus.
Content is addressed by BLAKE3 hash (CID). Files are stored in-memory by default;
a real node would use a persistent directory (see node.py install_services).
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Any

from hearthnet.bus.capability import CapabilityDescriptor, RouteRequest


def _cid(data: bytes) -> str:
    """BLAKE3 content hash.  Falls back to SHA-256 if blake3 is not installed."""
    try:
        import blake3  # type: ignore[import]

        return blake3.blake3(data).hexdigest()[:64]
    except ImportError:
        return "sha256:" + hashlib.sha256(data).hexdigest()


class FileService:
    """Content-addressed blob store (M07)."""

    name = "files"
    version = "1.0"

    def __init__(self, store_dir: Path | None = None) -> None:
        # In-memory store: cid -> {"data": bytes, "filename": str, "size": int, "added_at": str}
        self._store: dict[str, dict[str, Any]] = {}
        self._store_dir = store_dir
        if store_dir:
            store_dir.mkdir(parents=True, exist_ok=True)

    # ──────────────────────────────────────────────────────────────────────
    # Capabilities
    # ──────────────────────────────────────────────────────────────────────

    def capabilities(self) -> list[tuple]:
        return [
            (CapabilityDescriptor(name="file.put", max_concurrent=4), self.handle_put, None),
            (
                CapabilityDescriptor(name="file.get", max_concurrent=8, idempotent=True),
                self.handle_get,
                None,
            ),
            (
                CapabilityDescriptor(name="file.list", max_concurrent=8, idempotent=True),
                self.handle_list,
                None,
            ),
            (CapabilityDescriptor(name="file.delete", max_concurrent=4), self.handle_delete, None),
        ]

    # ──────────────────────────────────────────────────────────────────────
    # Handlers
    # ──────────────────────────────────────────────────────────────────────

    async def handle_put(self, req: RouteRequest) -> dict:
        """Store a file.  Input: {data_b64: str, filename: str}."""
        import base64

        inp = req.body.get("input", {})
        filename = inp.get("filename", "unnamed")
        data_b64 = inp.get("data_b64", "")
        try:
            data = base64.b64decode(data_b64)
        except Exception as exc:
            return {"error": f"invalid base64: {exc}"}
        cid = _cid(data)
        ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self._store[cid] = {
            "data": data,
            "filename": filename,
            "size": len(data),
            "added_at": ts,
            "uploader": req.caller,
        }
        if self._store_dir:
            (self._store_dir / cid).write_bytes(data)
        return {
            "output": {"cid": cid, "filename": filename, "size": len(data), "added_at": ts},
            "meta": {},
        }

    async def handle_get(self, req: RouteRequest) -> dict:
        """Retrieve a file by CID.  Output: {data_b64: str, filename: str, size: int}."""
        import base64

        cid = req.body.get("input", {}).get("cid", "")
        if not cid:
            return {"error": "cid required"}
        entry = self._store.get(cid)
        if entry is None and self._store_dir:
            p = self._store_dir / cid
            if p.exists():
                data = p.read_bytes()
                entry = {"data": data, "filename": cid[:16], "size": len(data), "added_at": ""}
        if entry is None:
            return {"error": f"not_found: {cid}"}
        return {
            "output": {
                "cid": cid,
                "data_b64": base64.b64encode(entry["data"]).decode(),
                "filename": entry["filename"],
                "size": entry["size"],
                "added_at": entry.get("added_at", ""),
            },
            "meta": {},
        }

    async def handle_list(self, req: RouteRequest) -> dict:
        """List all stored files.  Output: {files: [...]}."""
        files = [
            {
                "cid": cid,
                "filename": meta["filename"],
                "size": meta["size"],
                "added_at": meta.get("added_at", ""),
                "uploader": meta.get("uploader", ""),
            }
            for cid, meta in self._store.items()
        ]
        # Also scan disk store if available
        if self._store_dir:
            on_disk = {p.name for p in self._store_dir.iterdir() if p.is_file()}
            in_mem = set(self._store.keys())
            for cid in on_disk - in_mem:
                p = self._store_dir / cid
                files.append(
                    {
                        "cid": cid,
                        "filename": cid[:16],
                        "size": p.stat().st_size,
                        "added_at": "",
                        "uploader": "",
                    }
                )
        return {"output": {"files": files, "count": len(files)}, "meta": {}}

    async def handle_delete(self, req: RouteRequest) -> dict:
        """Delete a file by CID."""
        cid = req.body.get("input", {}).get("cid", "")
        if not cid:
            return {"error": "cid required"}
        existed = cid in self._store
        self._store.pop(cid, None)
        if self._store_dir:
            p = self._store_dir / cid
            if p.exists():
                p.unlink()
                existed = True
        return {"output": {"deleted": existed, "cid": cid}, "meta": {}}
