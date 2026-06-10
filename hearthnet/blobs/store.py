from __future__ import annotations

import json
import shutil
from pathlib import Path

from hearthnet.blobs.chunker import (
    BlobError,
    BlobManifest,
    ChunkRef,
    chunk_blob,
    reassemble,
    verify_chunk,
)


class BlobStore:
    """Sharded filesystem store.

    Layout::

        <root>/<aa>/<rest>.bin           — chunk binary
        <root>/<aa>/<rest>.manifest.json — blob manifest
        <root>/pinned.txt                — newline-separated pinned CIDs
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def put(self, data: bytes, filename: str | None = None) -> BlobManifest:
        """Chunk, hash, store all chunks, write manifest, return BlobManifest."""
        manifest, chunks_data = chunk_blob(data)
        # Attach filename (BlobManifest is frozen, rebuild with filename)
        manifest = BlobManifest(
            cid=manifest.cid,
            size_bytes=manifest.size_bytes,
            chunk_size_bytes=manifest.chunk_size_bytes,
            chunks=manifest.chunks,
            filename=filename,
        )
        for chunk_ref, chunk_data in zip(manifest.chunks, chunks_data, strict=False):
            path = self._blob_path(chunk_ref.cid)
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                path.write_bytes(chunk_data)

        mpath = self._manifest_path(manifest.cid)
        mpath.parent.mkdir(parents=True, exist_ok=True)
        mpath.write_text(
            json.dumps(self._manifest_to_dict(manifest), sort_keys=True, indent=2),
            encoding="utf-8",
        )
        return manifest

    def get(self, cid: str) -> bytes:
        """Read and reassemble blob. Raise BlobError('not_found') if missing."""
        manifest = self.get_manifest(cid)
        chunks: list[bytes] = []
        for chunk_ref in manifest.chunks:
            chunk_data = self.get_chunk(chunk_ref.cid)
            verify_chunk(chunk_data, chunk_ref.cid)
            chunks.append(chunk_data)
        return reassemble(chunks)

    def get_chunk(self, chunk_cid: str) -> bytes:
        """Read one chunk. Raise BlobError('not_found') if missing."""
        path = self._blob_path(chunk_cid)
        if not path.exists():
            raise BlobError("not_found", f"Chunk {chunk_cid} not found")
        return path.read_bytes()

    def has(self, cid: str) -> bool:
        """True iff blob manifest exists."""
        return self._manifest_path(cid).exists()

    def get_manifest(self, cid: str) -> BlobManifest:
        """Load manifest from disk."""
        path = self._manifest_path(cid)
        if not path.exists():
            raise BlobError("not_found", f"Blob {cid} not found")
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise BlobError("manifest_invalid", str(exc)) from exc
        return self._manifest_from_dict(raw)

    def list_blobs(self) -> list[BlobManifest]:
        """List all blob manifests."""
        manifests: list[BlobManifest] = []
        for mpath in self.root.rglob("*.manifest.json"):
            try:
                raw = json.loads(mpath.read_text(encoding="utf-8"))
                manifests.append(self._manifest_from_dict(raw))
            except Exception:
                pass
        return manifests

    def pin(self, cid: str) -> None:
        """Add CID to pinned.txt."""
        pinned = self._read_pinned()
        pinned.add(cid)
        self._write_pinned(pinned)

    def unpin(self, cid: str) -> None:
        """Remove CID from pinned.txt."""
        pinned = self._read_pinned()
        pinned.discard(cid)
        self._write_pinned(pinned)

    def gc(self, threshold: float = 0.80) -> int:
        """Remove unpinned blobs if disk usage > threshold. Returns count removed."""
        usage = shutil.disk_usage(self.root)
        if usage.used / usage.total <= threshold:
            return 0
        pinned = self._read_pinned()
        removed = 0
        for manifest in self.list_blobs():
            if manifest.cid in pinned:
                continue
            # Remove chunk files
            for chunk_ref in manifest.chunks:
                cpath = self._blob_path(chunk_ref.cid)
                if cpath.exists():
                    cpath.unlink()
            # Remove manifest
            mpath = self._manifest_path(manifest.cid)
            if mpath.exists():
                mpath.unlink()
            removed += 1
        return removed

    # ------------------------------------------------------------------
    # Path helpers
    # ------------------------------------------------------------------

    def _blob_path(self, cid: str) -> Path:
        """<root>/<aa>/<rest>.bin where aa = first 2 hex chars of CID hex."""
        hex_part = self._hex_part(cid)
        shard = hex_part[:2]
        rest = hex_part[2:]
        return self.root / shard / f"{rest}.bin"

    def _manifest_path(self, cid: str) -> Path:
        hex_part = self._hex_part(cid)
        shard = hex_part[:2]
        rest = hex_part[2:]
        return self.root / shard / f"{rest}.manifest.json"

    def _hex_part(self, cid: str) -> str:
        """Extract hex from 'blake3:<hex>' or 'sha256:<hex>'."""
        return cid.split(":", 1)[1]

    # ------------------------------------------------------------------
    # Serialization helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _manifest_to_dict(m: BlobManifest) -> dict:
        return {
            "cid": m.cid,
            "size_bytes": m.size_bytes,
            "chunk_size_bytes": m.chunk_size_bytes,
            "filename": m.filename,
            "chunks": [
                {"index": c.index, "cid": c.cid, "size_bytes": c.size_bytes} for c in m.chunks
            ],
        }

    @staticmethod
    def _manifest_from_dict(raw: dict) -> BlobManifest:
        chunks = [
            ChunkRef(index=c["index"], cid=c["cid"], size_bytes=c["size_bytes"])
            for c in raw.get("chunks", [])
        ]
        return BlobManifest(
            cid=raw["cid"],
            size_bytes=raw["size_bytes"],
            chunk_size_bytes=raw["chunk_size_bytes"],
            chunks=chunks,
            filename=raw.get("filename"),
        )

    # ------------------------------------------------------------------
    # Pinned helpers
    # ------------------------------------------------------------------

    def _pinned_path(self) -> Path:
        return self.root / "pinned.txt"

    def _read_pinned(self) -> set[str]:
        p = self._pinned_path()
        if not p.exists():
            return set()
        return {line.strip() for line in p.read_text(encoding="utf-8").splitlines() if line.strip()}

    def _write_pinned(self, pinned: set[str]) -> None:
        self._pinned_path().write_text("\n".join(sorted(pinned)), encoding="utf-8")
