from __future__ import annotations

from hearthnet.bus.capability import CapabilityDescriptor, RouteRequest
from hearthnet.constants import EMBED_MAX_CHARS, EMBED_MAX_TEXTS
from hearthnet.services.embedding.backends import EmbeddingBackend, SimpleHashBackend


class EmbeddingService:
    name = "embedding"
    version = "1.0"

    def __init__(self, backend: EmbeddingBackend | None = None) -> None:
        self._backend: EmbeddingBackend = backend or SimpleHashBackend()

    def capabilities(self) -> list[tuple]:
        descriptor = CapabilityDescriptor(
            name="embed.text",
            version=(1, 0),
            stability="stable",
            params={"model": self._backend.model, "dim": self._backend.dim},
            max_concurrent=8,
            trust_required="member",
            timeout_seconds=30,
            idempotent=True,
        )
        return [(descriptor, self.handle_embed, self._params_compatible)]

    def _params_compatible(self, offered: dict, requested: dict) -> bool:
        req_model = requested.get("model")
        return not req_model or req_model == offered.get("model")

    async def handle_embed(self, req: RouteRequest) -> dict:
        inp = req.body.get("input", {})
        texts = inp.get("texts", [])
        normalize = inp.get("normalize", True)

        if len(texts) > EMBED_MAX_TEXTS:
            return {
                "error": "bad_request",
                "message": f"Too many texts (max {EMBED_MAX_TEXTS})",
            }

        for t in texts:
            if len(t) > EMBED_MAX_CHARS:
                return {
                    "error": "bad_request",
                    "message": f"Text too long (max {EMBED_MAX_CHARS} chars)",
                }

        if not texts:
            return {
                "output": {
                    "embeddings": [],
                    "model": self._backend.model,
                    "dim": self._backend.dim,
                },
                "meta": {},
            }

        try:
            embeddings = await self._backend.embed(texts, normalize=normalize)
        except Exception as exc:
            return {"error": "internal_error", "message": str(exc)}

        return {
            "output": {
                "embeddings": embeddings,
                "model": self._backend.model,
                "dim": self._backend.dim,
            },
            "meta": {"count": len(embeddings)},
        }
