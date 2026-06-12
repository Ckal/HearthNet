"""Ollama HTTP backend: http://localhost:11434"""

from __future__ import annotations

from hearthnet.services.llm.backends.base import BackendModel, ChatResult, Token
from hearthnet.services.llm.tokenizers import model_family


def _family(model_name: str) -> str:
    return model_family(model_name)


class OllamaBackend:
    name = "ollama"

    def __init__(self, base_url: str = "http://localhost:11434", default_model: str = "") -> None:
        self._base_url = base_url.rstrip("/")
        self._default_model = default_model
        self.models: list[BackendModel] = []

    def is_available(self) -> bool:
        try:
            import httpx

            resp = httpx.get(f"{self._base_url}/api/tags", timeout=3.0)
            return resp.status_code == 200
        except Exception:
            return False

    async def _list_models(self) -> list[str]:
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{self._base_url}/api/tags", timeout=5.0)
                data = resp.json()
                return [m["name"] for m in data.get("models", [])]
        except Exception:
            return []

    async def warm(self) -> None:
        model_names = await self._list_models()
        self.models = [
            BackendModel(
                name=m,
                family=_family(m),
                context_length=4096,
                requires_internet=False,
            )
            for m in model_names
        ]

    async def chat(
        self,
        messages: list[dict],
        *,
        model: str,
        stream: bool = False,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        **kwargs,
    ):
        import time

        import httpx

        model = model or self._default_model
        t0 = time.monotonic()

        payload = {
            "model": model,
            "messages": messages,
            "stream": stream,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }

        if not stream:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(f"{self._base_url}/api/chat", json=payload)
                resp.raise_for_status()
                data = resp.json()
                text = data.get("message", {}).get("content", "")
                ms = int((time.monotonic() - t0) * 1000)
                return ChatResult(
                    text=text,
                    tokens_in=0,
                    tokens_out=len(text.split()),
                    model=model,
                    ms=ms,
                )
        else:
            return self._stream_chat(payload, t0)

    async def _stream_chat(self, payload: dict, t0: float):
        import json

        import httpx

        async with (
            httpx.AsyncClient(timeout=120.0) as client,
            client.stream("POST", f"{self._base_url}/api/chat", json=payload) as resp,
        ):
            async for line in resp.aiter_lines():
                if line:
                    try:
                        data = json.loads(line)
                        text = data.get("message", {}).get("content", "")
                        done = data.get("done", False)
                        if text:
                            yield Token(text=text, stop=done)
                    except json.JSONDecodeError:
                        pass

    async def complete(self, prompt: str, *, model: str, stream: bool = False, **kwargs):
        messages = [{"role": "user", "content": prompt}]
        return await self.chat(messages, model=model, stream=stream, **kwargs)

    async def close(self) -> None:
        pass

    def health(self) -> dict:
        return {
            "backend": "ollama",
            "available": self.is_available(),
            "url": self._base_url,
        }
