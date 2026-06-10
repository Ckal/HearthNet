"""llama-cpp-python in-process backend."""
from __future__ import annotations

from hearthnet.services.llm.backends.base import BackendModel, ChatResult, Token
from hearthnet.services.llm.tokenizers import model_family


def _family(model_name: str) -> str:
    return model_family(model_name)


class LlamaCppBackend:
    name = "llama_cpp"

    def __init__(
        self, model_path: str, n_ctx: int = 4096, n_gpu_layers: int = -1
    ) -> None:
        self._model_path = model_path
        self._n_ctx = n_ctx
        self._n_gpu_layers = n_gpu_layers
        self._llm = None
        model_name = model_path.split("/")[-1].split(".")[0]
        self.models = [
            BackendModel(
                name=model_name,
                family=_family(model_name),
                context_length=n_ctx,
                requires_internet=False,
            )
        ]

    def is_available(self) -> bool:
        try:
            from pathlib import Path

            import llama_cpp

            return Path(self._model_path).exists()
        except ImportError:
            return False

    async def warm(self) -> None:
        if not self.is_available():
            return
        import asyncio

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._load_model)

    def _load_model(self) -> None:
        from llama_cpp import Llama

        self._llm = Llama(
            model_path=self._model_path,
            n_ctx=self._n_ctx,
            n_gpu_layers=self._n_gpu_layers,
            verbose=False,
        )

    async def chat(
        self,
        messages: list[dict],
        *,
        model: str = "",
        stream: bool = False,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        **kwargs,
    ):
        import asyncio
        import time

        if self._llm is None:
            await self.warm()
        if self._llm is None:
            raise RuntimeError("llama.cpp model not loaded")
        t0 = time.monotonic()
        loop = asyncio.get_event_loop()
        if not stream:
            result = await loop.run_in_executor(
                None,
                lambda: self._llm.create_chat_completion(
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                ),
            )
            text = result["choices"][0]["message"]["content"]
            ms = int((time.monotonic() - t0) * 1000)
            return ChatResult(
                text=text,
                tokens_in=result["usage"]["prompt_tokens"],
                tokens_out=result["usage"]["completion_tokens"],
                model=self.models[0].name,
                ms=ms,
            )
        else:
            return self._stream_chat(messages, temperature, max_tokens)

    async def _stream_chat(self, messages, temperature, max_tokens):
        import asyncio

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: self._llm.create_chat_completion(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            ),
        )
        for chunk in result:
            delta = chunk["choices"][0].get("delta", {})
            text = delta.get("content", "")
            done = chunk["choices"][0]["finish_reason"] is not None
            if text or done:
                yield Token(text=text, stop=done)

    async def complete(
        self, prompt: str, *, model: str = "", stream: bool = False, **kwargs
    ):
        messages = [{"role": "user", "content": prompt}]
        return await self.chat(messages, model=model, stream=stream, **kwargs)

    async def close(self) -> None:
        self._llm = None

    def health(self) -> dict:
        return {
            "backend": "llama_cpp",
            "model_path": self._model_path,
            "loaded": self._llm is not None,
        }
