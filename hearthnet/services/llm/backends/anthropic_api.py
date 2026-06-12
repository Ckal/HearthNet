"""M04 — Anthropic API backend (cloud, opt-in).

Uses Anthropic's Messages API: https://api.anthropic.com/v1/messages
Requires ANTHROPIC_API_KEY env var. Online-only; M09 deregisters when offline.
"""

from __future__ import annotations

import json
import os

from hearthnet.services.llm.backends.base import BackendModel, Token


class AnthropicApiBackend:
    """Anthropic Claude API — cloud LLM endpoint.

    Online-only opt-in fallback. Set ANTHROPIC_API_KEY to enable.
    Supports: claude-3-haiku-20240307 (fast/cheap), claude-3-sonnet-20240229.
    """

    name = "anthropic_api"
    _ANTHROPIC_VERSION = "2023-06-01"

    def __init__(
        self,
        model: str = "claude-3-haiku-20240307",
        api_key_env: str = "ANTHROPIC_API_KEY",
        base_url: str = "https://api.anthropic.com",
    ) -> None:
        self._model = model
        self._api_key_env = api_key_env
        self._base_url = base_url.rstrip("/")
        self.models = [
            BackendModel(
                name="claude-3-haiku-20240307",
                family="claude",
                context_length=200_000,
                requires_internet=True,
            ),
            BackendModel(
                name="claude-3-sonnet-20240229",
                family="claude",
                context_length=200_000,
                requires_internet=True,
            ),
        ]

    def _get_key(self) -> str:
        return os.environ.get(self._api_key_env, "")

    def is_available(self) -> bool:
        return bool(self._get_key())

    async def warm(self) -> None:
        pass

    async def health(self) -> dict:
        return {"ok": self.is_available(), "backend": self.name, "model": self._model}

    async def chat(self, messages: list[dict], *, max_tokens: int = 1024, **kwargs):
        """Async generator yielding Token objects."""
        import urllib.error
        import urllib.request

        key = self._get_key()
        if not key:
            raise RuntimeError(f"{self._api_key_env} not set; Anthropic API unavailable")

        # Separate system message
        system = ""
        user_messages = []
        for m in messages:
            if m.get("role") == "system":
                system = m.get("content", "")
            else:
                user_messages.append({"role": m["role"], "content": m.get("content", "")})

        payload: dict = {
            "model": self._model,
            "max_tokens": max_tokens,
            "messages": user_messages or [{"role": "user", "content": "Hi"}],
        }
        if system:
            payload["system"] = system

        url = f"{self._base_url}/v1/messages"
        req = urllib.request.Request(  # nosec B310
            url,
            data=json.dumps(payload).encode(),
            headers={
                "x-api-key": key,
                "anthropic-version": self._ANTHROPIC_VERSION,
                "content-type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:  # nosec B310
                data = json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")
            raise RuntimeError(f"Anthropic API {exc.code}: {body}") from exc
        except OSError as exc:
            raise RuntimeError(f"Anthropic API connection error: {exc}") from exc

        text = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                text += block.get("text", "")

        yield Token(text=text, logprob=None, finish_reason=data.get("stop_reason", "stop"))

    async def complete(self, prompt: str, *, max_tokens: int = 512, **kwargs):
        """Async generator yielding Token objects."""
        async for tok in self.chat([{"role": "user", "content": prompt}], max_tokens=max_tokens):
            yield tok

    async def close(self) -> None:
        pass
