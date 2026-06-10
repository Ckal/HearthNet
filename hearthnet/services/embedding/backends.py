from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class EmbeddingBackend(Protocol):
    name: str
    model: str
    dim: int
    max_input: int

    async def embed(self, texts: list[str], *, normalize: bool = True) -> list[list[float]]: ...
    async def warm(self) -> None: ...
    async def close(self) -> None: ...
    def health(self) -> dict: ...


class SimpleHashBackend:
    """Deterministic test backend using hash-based pseudo-embeddings. No ML deps."""

    name = "simple"
    model = "hash-16"
    dim = 16
    max_input = 8192

    async def embed(self, texts: list[str], *, normalize: bool = True) -> list[list[float]]:
        """Hash each text to a 16-dim float vector. Deterministic. For testing."""
        import hashlib
        import struct

        result = []
        for text in texts:
            # SHA-512 yields 64 bytes → 16 × 4-byte floats
            h = hashlib.sha512(text.encode()).digest()
            vec = [struct.unpack_from("f", h, i)[0] for i in range(0, 64, 4)]
            if normalize:
                norm = sum(x**2 for x in vec) ** 0.5 or 1.0
                vec = [x / norm for x in vec]
            result.append(vec)
        return result

    async def warm(self) -> None:
        pass

    async def close(self) -> None:
        pass

    def health(self) -> dict:
        return {"backend": "simple", "status": "ok"}


class SentenceTransformerBackend:
    """Local backend using sentence-transformers + torch."""

    name = "sentence_transformers"

    def __init__(self, model: str, device: str = "auto") -> None:
        self.model = model
        self.dim = 384  # default for bge-small
        self.max_input = 8192
        self._model = None
        self._device = device

    async def embed(self, texts: list[str], *, normalize: bool = True) -> list[list[float]]:
        """Load model lazily on first embed call."""
        if self._model is None:
            await self.warm()
        import asyncio

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._embed_sync, texts, normalize)

    def _embed_sync(self, texts: list[str], normalize: bool) -> list[list[float]]:
        embeddings = self._model.encode(
            texts, normalize_embeddings=normalize, show_progress_bar=False
        )
        return [e.tolist() for e in embeddings]

    async def warm(self) -> None:
        """Load the model in a thread to avoid blocking event loop."""
        import asyncio

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._load_model)

    def _load_model(self) -> None:
        try:
            from sentence_transformers import SentenceTransformer

            device = self._device
            if device == "auto":
                try:
                    import torch

                    device = "cuda" if torch.cuda.is_available() else "cpu"
                except ImportError:
                    device = "cpu"
            self._model = SentenceTransformer(self.model, device=device)
            self.dim = self._model.get_sentence_embedding_dimension() or 384
        except ImportError as e:
            raise RuntimeError(f"sentence-transformers not installed: {e}") from e

    async def close(self) -> None:
        pass

    def health(self) -> dict:
        return {
            "backend": "sentence_transformers",
            "model": self.model,
            "loaded": self._model is not None,
        }
