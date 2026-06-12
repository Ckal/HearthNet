"""OpenAI-compatible HTTP backend. ONLINE ONLY — opt-in fallback."""

from __future__ import annotations

from hearthnet.services.llm.backends.base import BackendModel, ChatResult, Token
from hearthnet.services.llm.tokenizers import model_family


def _family(model_name: str) -> str:
    return model_family(model_name)


class OpenAICompatBackend:
    """OpenAI-compatible HTTP backend. Only used when explicitly configured AND online.
    Never the default local path."""

    name = "openai_compat"

    def __init__(
        self,
        base_url: str = "https://api.openai.com/v1",
        api_key_env: str = "OPENAI_API_KEY",
        model: str = "gpt-3.5-turbo",
    ) -> None:
        self._base_url = base_url
        self._api_key_env = api_key_env
        self._model = model
        self.models = [
            BackendModel(
                name=model,
                family="gpt",
                context_length=16385,
                requires_internet=True,
            )
        ]

    def _get_key(self) -> str:
        import os

        key = os.environ.get(self._api_key_env, "")
        if not key:
            raise RuntimeError(f"API key env {self._api_key_env} not set")
        return key

    def is_available(self) -> bool:
        import os

        return bool(os.environ.get(self._api_key_env))

    async def warm(self) -> None:
        pass

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
        import time

        import httpx

        model = model or self._model
        t0 = time.monotonic()
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
        }
        headers = {
            "Authorization": f"Bearer {self._get_key()}",
            "Content-Type": "application/json",
        }

        if not stream:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{self._base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()
                text = data["choices"][0]["message"]["content"]
                ms = int((time.monotonic() - t0) * 1000)
                usage = data.get("usage", {})
                return ChatResult(
                    text=text,
                    tokens_in=usage.get("prompt_tokens", 0),
                    tokens_out=usage.get("completion_tokens", 0),
                    model=model,
                    ms=ms,
                )
        else:
            return self._stream_chat(payload, headers, model, t0)

    async def _stream_chat(self, payload, headers, model, t0):
        import json

        import httpx

        payload["stream"] = True
        async with httpx.AsyncClient(timeout=60.0) as client, client.stream(
            "POST",
            f"{self._base_url}/chat/completions",
            json=payload,
            headers=headers,
        ) as resp:
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    raw = line[6:]
                    if raw == "[DONE]":
                        yield Token(text="", stop=True)
                        return
                    try:
                        data = json.loads(raw)
                        delta = data["choices"][0].get("delta", {})
                        text = delta.get("content", "")
                        if text:
                            yield Token(text=text, stop=False)
                    except Exception:
                        pass

    async def complete(self, prompt: str, *, model: str = "", stream: bool = False, **kwargs):
        return await self.chat(
            [{"role": "user", "content": prompt}], model=model, stream=stream, **kwargs
        )

    async def close(self) -> None:
        pass

    def health(self) -> dict:
        return {
            "backend": "openai_compat",
            "available": self.is_available(),
            "url": self._base_url,
        }
