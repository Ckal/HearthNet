from __future__ import annotations

from hearthnet.blobs.chunker import BlobError, BlobManifest, verify_chunk
from hearthnet.blobs.store import BlobStore


class TransferManager:
    """Coordinates parallel chunk fetch from multiple peer sources.

    MVP: fetch from one source at a time (parallel is Phase 2 optimization).
    """

    def __init__(self, store: BlobStore, http_client=None) -> None:
        self.store = store
        self._http_client = http_client

    async def fetch(self, cid: str, sources: list[str]) -> BlobManifest:
        """Fetch a blob from one of the sources (tries in order).

        sources: list of base URLs like 'https://host:7080'
        """
        last_exc: Exception | None = None
        for base_url in sources:
            try:
                return await self._fetch_from(cid, base_url)
            except Exception as exc:
                last_exc = exc
        raise BlobError(
            "not_found",
            f"Could not fetch {cid} from any source. Last error: {last_exc}",
        )

    async def _fetch_from(self, cid: str, base_url: str) -> BlobManifest:
        """Fetch blob manifest + all chunks from base_url/file/chunks/<chunk_cid>."""
        import json

        client = self._http_client
        if client is None:
            try:
                import httpx  # type: ignore[import]

                client = httpx.AsyncClient()
            except ImportError as exc:
                raise BlobError(
                    "io_error", "httpx is required for TransferManager network fetch"
                ) from exc

        manifest_url = f"{base_url.rstrip('/')}/file/manifest/{cid}"
        try:
            resp = await client.get(manifest_url, timeout=30)
            resp.raise_for_status()
            raw = resp.json()
        except Exception as exc:
            raise BlobError(
                "io_error", f"Failed to fetch manifest from {manifest_url}: {exc}"
            ) from exc

        from hearthnet.blobs.store import BlobStore as _BS

        manifest = _BS._manifest_from_dict(raw)

        for chunk_ref in manifest.chunks:
            if self.store._blob_path(chunk_ref.cid).exists():
                continue  # already have it
            chunk_url = f"{base_url.rstrip('/')}/file/chunks/{chunk_ref.cid}"
            try:
                resp = await client.get(chunk_url, timeout=60)
                resp.raise_for_status()
                chunk_data = resp.content
            except Exception as exc:
                raise BlobError(
                    "io_error", f"Failed to fetch chunk {chunk_ref.cid}: {exc}"
                ) from exc
            verify_chunk(chunk_data, chunk_ref.cid)
            path = self.store._blob_path(chunk_ref.cid)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(chunk_data)

        # Write manifest if not already stored
        if not self.store.has(manifest.cid):
            mpath = self.store._manifest_path(manifest.cid)
            mpath.parent.mkdir(parents=True, exist_ok=True)
            mpath.write_text(
                json.dumps(_BS._manifest_to_dict(manifest), sort_keys=True, indent=2),
                encoding="utf-8",
            )

        return manifest
