"""Local HuggingFace Transformers backend.

ZeroGPU note: When running on HF Spaces with ZeroGPU, CUDA must only be
accessed inside a ``@spaces.GPU``-decorated function. This backend detects
the ``SPACE_HOST`` environment variable and forces CPU (``device=-1``) to
avoid triggering ``torch._C._cuda_init`` at load time.  GPU acceleration
within the Space would require wrapping inference in ``@spaces.GPU``.
"""

from __future__ import annotations

import os

from hearthnet.services.llm.backends.base import BackendModel, ChatResult
from hearthnet.services.llm.tokenizers import model_family

# If running on HF Space, force CPU to avoid ZeroGPU CUDA-init errors
_ON_HF_SPACE: bool = bool(os.getenv("SPACE_HOST"))


def _family(model_name: str) -> str:
    return model_family(model_name)


class HfLocalBackend:
    name = "hf_local"

    def __init__(self, model: str = "microsoft/DialoGPT-small", device: str = "auto") -> None:
        self._model_name = model
        # Force CPU on HF Spaces to prevent ZeroGPU CUDA-init outside @spaces.GPU
        self._device = "cpu" if _ON_HF_SPACE else device
        self._pipeline = None
        self.models = [
            BackendModel(
                name=model,
                family=_family(model),
                context_length=2048,
                requires_internet=False,
            )
        ]

    def is_available(self) -> bool:
        try:
            import transformers  # noqa: F401

            return True
        except ImportError:
            return False

    async def warm(self) -> None:
        if not self.is_available():
            return
        import asyncio

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._load)

    def _load(self) -> None:
        from transformers import pipeline

        if self._device == "cpu":
            device = -1
        elif self._device == "cuda":
            device = 0
        else:
            # "auto" — safe CUDA check (only reaches here when NOT on HF Space)
            device = -1
            try:
                import torch

                device = 0 if torch.cuda.is_available() else -1
            except ImportError:
                pass
        self._pipeline = pipeline(
            "text-generation",
            model=self._model_name,
            device=device,
            # Disable auto device_map to keep explicit CPU/GPU control
            model_kwargs={"low_cpu_mem_usage": True},
        )

    async def chat(
        self,
        messages: list[dict],
        *,
        model: str = "",
        stream: bool = False,
        temperature: float = 0.7,
        max_tokens: int = 256,
        **kwargs,
    ):
        import asyncio
        import time

        if self._pipeline is None:
            await self.warm()
        if self._pipeline is None:
            raise RuntimeError("HF model not loaded")
        t0 = time.monotonic()
        prompt = "\n".join(f"{m['role']}: {m['content']}" for m in messages) + "\nassistant:"
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            lambda: self._pipeline(
                prompt,
                max_new_tokens=max_tokens,
                temperature=temperature,
                do_sample=True,
                return_full_text=False,
            ),
        )
        text = result[0]["generated_text"] if result else ""
        ms = int((time.monotonic() - t0) * 1000)
        return ChatResult(
            text=text,
            tokens_in=len(prompt.split()),
            tokens_out=len(text.split()),
            model=self._model_name,
            ms=ms,
        )

    async def complete(self, prompt: str, *, model: str = "", stream: bool = False, **kwargs):
        return await self.chat(
            [{"role": "user", "content": prompt}], model=model, stream=stream, **kwargs
        )

    async def close(self) -> None:
        self._pipeline = None

    def health(self) -> dict:
        return {
            "backend": "hf_local",
            "model": self._model_name,
            "loaded": self._pipeline is not None,
            "device": self._device,
            "on_hf_space": _ON_HF_SPACE,
        }


    async def chat(
        self,
        messages: list[dict],
        *,
        model: str = "",
        stream: bool = False,
        temperature: float = 0.7,
        max_tokens: int = 256,
        **kwargs,
    ):
        import asyncio
        import time

        if self._pipeline is None:
            await self.warm()
        if self._pipeline is None:
            raise RuntimeError("HF model not loaded")
        t0 = time.monotonic()
        prompt = "\n".join(f"{m['role']}: {m['content']}" for m in messages) + "\nassistant:"
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            lambda: self._pipeline(
                prompt,
                max_new_tokens=max_tokens,
                temperature=temperature,
                do_sample=True,
                return_full_text=False,
            ),
        )
        text = result[0]["generated_text"] if result else ""
        ms = int((time.monotonic() - t0) * 1000)
        return ChatResult(
            text=text,
            tokens_in=len(prompt.split()),
            tokens_out=len(text.split()),
            model=self._model_name,
            ms=ms,
        )

    async def complete(self, prompt: str, *, model: str = "", stream: bool = False, **kwargs):
        return await self.chat(
            [{"role": "user", "content": prompt}], model=model, stream=stream, **kwargs
        )

    async def close(self) -> None:
        self._pipeline = None

    def health(self) -> dict:
        return {
            "backend": "hf_local",
            "model": self._model_name,
            "loaded": self._pipeline is not None,
        }
