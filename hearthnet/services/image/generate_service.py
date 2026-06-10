from __future__ import annotations

import base64
from typing import Any

from hearthnet.bus.capability import CapabilityDescriptor, RouteRequest
from hearthnet.services.image.backends.base import ImageGenerateBackend, GenerationResult


class ImageGenerateService:
    """Service wrapping image-generation backends.

    Registers: img.generate@1.0
    """

    name = "image.generate"

    def __init__(
        self,
        backends: list[ImageGenerateBackend] | None = None,
        bus: Any = None,
    ) -> None:
        self._backends: list[ImageGenerateBackend] = backends if backends is not None else []
        self._bus = bus
        self._by_name: dict[str, ImageGenerateBackend] = {b.name: b for b in self._backends}

    # ── Service registration ──────────────────────────────────────────────────

    def capabilities(self) -> list[tuple]:
        return [
            (
                CapabilityDescriptor(
                    name="img.generate",
                    max_concurrent=1,
                    idempotent=False,
                    timeout_seconds=120,
                ),
                self.generate,
                None,
            ),
        ]

    def register(self, bus: Any) -> None:
        self._bus = bus
        for cap, handler, predicate in self.capabilities():
            bus.register_local(cap, handler, predicate)

    # ── Handler ───────────────────────────────────────────────────────────────

    async def generate(self, req: RouteRequest) -> dict:
        if not self._backends:
            return {
                "error": "unavailable",
                "message": "no image generation backends installed",
            }

        params: dict = req.body.get("input", {})
        prompt: str | None = params.get("prompt")
        if not prompt:
            return {"error": "bad_request", "message": "prompt required"}

        width: int = int(params.get("width", 512))
        height: int = int(params.get("height", 512))
        steps: int = int(params.get("steps", 20))
        lora: str | None = params.get("lora")
        backend_name: str | None = params.get("backend")

        # Clamp dimensions to sane limits
        width = max(64, min(width, 2048))
        height = max(64, min(height, 2048))
        steps = max(1, min(steps, 200))

        # Select backend
        backend: ImageGenerateBackend | None = None
        if backend_name:
            backend = self._by_name.get(backend_name)
            if backend is None:
                return {"error": "bad_request", "message": f"unknown backend: {backend_name}"}
        else:
            backend = self._backends[0]

        result: GenerationResult = await backend.generate(
            prompt, width=width, height=height, steps=steps, lora=lora
        )
        image_b64 = base64.b64encode(result.image_bytes).decode("ascii")
        return {
            "output": {
                "image_b64": image_b64,
                "width": result.width,
                "height": result.height,
                "backend": result.backend,
                "ms": result.ms,
            },
            "meta": {},
        }

    def health(self) -> dict:
        return {
            "service": self.name,
            "backends": [b.health() for b in self._backends],
            "available": len(self._backends) > 0,
        }
