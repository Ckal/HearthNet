from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

CHUNK_SIZE_BYTES = 256 * 1024  # 256 KB


class BlobError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


@dataclass(frozen=True)
class ChunkRef:
    index: int
    cid: str  # "blake3:<hex>" or "sha256:<hex>"
    size_bytes: int


@dataclass(frozen=True)
class BlobManifest:
    cid: str  # merkle root CID
    size_bytes: int
    chunk_size_bytes: int
    chunks: list[ChunkRef]
    filename: str | None  # advisory only


def hash_bytes(data: bytes) -> str:
    """Hash with BLAKE3 if available, else SHA256. Returns 'blake3:<hex>' or 'sha256:<hex>'."""
    try:
        import blake3

        return "blake3:" + blake3.blake3(data).hexdigest()
    except ImportError:
        return "sha256:" + hashlib.sha256(data).hexdigest()


def chunk_blob(
    data: bytes, *, chunk_size: int = CHUNK_SIZE_BYTES
) -> tuple[BlobManifest, list[bytes]]:
    """Split data into chunks. Compute per-chunk CID and merkle-root CID."""
    chunks_data: list[bytes] = []
    chunk_refs: list[ChunkRef] = []

    offset = 0
    index = 0
    while offset < len(data) or index == 0:
        piece = data[offset : offset + chunk_size]
        cid = hash_bytes(piece)
        chunk_refs.append(ChunkRef(index=index, cid=cid, size_bytes=len(piece)))
        chunks_data.append(piece)
        offset += chunk_size
        index += 1
        if offset >= len(data):
            break

    merkle_root = hash_bytes(b"\n".join(sorted(c.cid.encode() for c in chunk_refs)))

    manifest = BlobManifest(
        cid=merkle_root,
        size_bytes=len(data),
        chunk_size_bytes=chunk_size,
        chunks=chunk_refs,
        filename=None,
    )
    return manifest, chunks_data


def manifest_cid(manifest: BlobManifest) -> str:
    """CID of canonical JSON of {chunks: [{cid,size_bytes}], size_bytes, chunk_size_bytes}."""
    payload = {
        "chunk_size_bytes": manifest.chunk_size_bytes,
        "chunks": [{"cid": c.cid, "size_bytes": c.size_bytes} for c in manifest.chunks],
        "size_bytes": manifest.size_bytes,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )
    return hash_bytes(raw)


def reassemble(chunks: list[bytes]) -> bytes:
    """Concat chunks in index order."""
    return b"".join(chunks)


def verify_chunk(data: bytes, expected_cid: str) -> None:
    """Raise BlobError('hash_mismatch') if hash(data) != expected_cid."""
    actual = hash_bytes(data)
    if actual != expected_cid:
        raise BlobError("hash_mismatch", f"Expected {expected_cid}, got {actual}")
