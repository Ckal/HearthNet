from __future__ import annotations

import base64
import time
from typing import Any

from hearthnet.bus.capability import CapabilityDescriptor, RouteRequest
from hearthnet.services.image.backends.base import ImageDescribeBackend, ImageDescription
from hearthnet.services.image.backends.florence2 import Florence2Backend


class ImageDescribeService:
    """Service wrapping image-description backends.

    Registers: img.describe@1.0
    """

    name = "image.describe"

    def __init__(self, backends: list[ImageDescribeBackend] | None = None, bus: Any = None) -> None:
        if backends is not None:
            self._backends: list[ImageDescribeBackend] = backends
        else:
            self._backends = [Florence2Backend()]
        self._bus = bus
        self._by_name: dict[str, ImageDescribeBackend] = {b.name: b for b in self._backends}

    # ── Service registration ──────────────────────────────────────────────────

    def capabilities(self) -> list[tuple]:
        return [
            (
                CapabilityDescriptor(
                    name="img.describe",
                    max_concurrent=2,
                    idempotent=True,
                    timeout_seconds=60,
                ),
                self.describe,
                None,
            ),
        ]

    def register(self, bus: Any) -> None:
        self._bus = bus
        for cap, handler, predicate in self.capabilities():
            bus.register_local(cap, handler, predicate)

    # ── Handler ───────────────────────────────────────────────────────────────

    async def describe(self, req: RouteRequest) -> dict:
        params: dict = req.body.get("input", {})

        image_cid: str | None = params.get("image_cid")
        image_b64: str | None = params.get("image_b64")
        mode: str = params.get("mode", "caption")
        backend_name: str | None = params.get("backend")

        # Resolve image bytes
        image_bytes: bytes | None = None
        if image_b64:
            try:
                image_bytes = base64.b64decode(image_b64)
            except Exception as exc:
                return {"error": "bad_request", "message": f"invalid image_b64: {exc}"}
        elif image_cid:
            # Attempt to resolve from blob store if available
            try:
                from hearthnet.blobs.store import BlobStore  # type: ignore[import-untyped]
                # If bus has a blob store reference, use it; otherwise return error
                if hasattr(self._bus, "blob_store"):
                    store: Any = self._bus.blob_store
                    image_bytes = store.get(image_cid)
            except Exception:
                pass
            if image_bytes is None:
                return {"error": "not_found", "message": f"blob {image_cid} not found"}
        else:
            return {"error": "bad_request", "message": "image_cid or image_b64 required"}

        # Select backend
        backend: ImageDescribeBackend | None = None
        if backend_name:
            backend = self._by_name.get(backend_name)
            if backend is None:
                return {"error": "bad_request", "message": f"unknown backend: {backend_name}"}
        elif self._backends:
            backend = self._backends[0]
        else:
            return {"error": "unavailable", "message": "no image backends configured"}

        result: ImageDescription = await backend.describe(image_bytes, mode=mode)
        return {
            "output": {
                "caption": result.caption,
                "tags": result.tags,
                "objects": result.objects,
                "ocr_text": result.ocr_text,
                "backend": result.backend,
                "ms": result.ms,
            },
            "meta": {},
        }

    def health(self) -> dict:
        return {
            "service": self.name,
            "backends": [b.health() for b in self._backends],
        }
