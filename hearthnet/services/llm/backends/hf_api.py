"""M04 — Hugging Face Inference API backend (cloud, opt-in).

Uses the HF Inference API: https://api-inference.huggingface.co/
Requires HEARTHNET_HF_TOKEN env var. Online-only; M09 deregisters when offline.
"""

from __future__ import annotations

import os
from hearthnet.services.llm.backends.base import BackendModel, ChatResult, Token


class HfApiBackend:
    """Hugging Face Inference API — cloud LLM endpoint.

    Online-only fallback. Set HEARTHNET_HF_TOKEN to enable.
    Default model: HuggingFaceH4/zephyr-7b-beta (public, instruction-tuned).
    """

    name = "hf_api"

    def __init__(
        self,
        model: str = "HuggingFaceH4/zephyr-7b-beta",
        api_key_env: str = "HEARTHNET_HF_TOKEN",
        base_url: str = "https://api-inference.huggingface.co",
    ) -> None:
        self._model = model
        self._api_key_env = api_key_env
        self._base_url = base_url.rstrip("/")
        self.models = [
            BackendModel(
                name=model,
                family="hf_api",
                context_length=4096,
                requires_internet=True,
            )
        ]

    def _get_key(self) -> str:
        return os.environ.get(self._api_key_env, "")

    def is_available(self) -> bool:
        return bool(self._get_key())

    async def warm(self) -> None:
        pass

    async def health(self) -> dict:
        return {"ok": self.is_available(), "backend": self.name, "model": self._model}

    async def chat(self, messages: list[dict], *, max_tokens: int = 512, **kwargs):
        """Async generator yielding Token objects (streaming)."""
        import json
        import urllib.request

        key = self._get_key()
        if not key:
            raise RuntimeError(f"{self._api_key_env} not set; HF Inference API unavailable")

        # Convert chat messages to a single prompt for text-generation endpoint
        prompt = "\n".join(
            f"{'User' if m.get('role') == 'user' else 'Assistant'}: {m.get('content', '')}"
            for m in messages
        )
        prompt += "\nAssistant:"

        url = f"{self._base_url}/models/{self._model}"
        payload = json.dumps({
            "inputs": prompt,
            "parameters": {"max_new_tokens": max_tokens, "return_full_text": False},
        }).encode()
        req = urllib.request.Request(  # nosec B310
            url,
            data=payload,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:  # nosec B310
                data = json.loads(resp.read())
        except Exception as exc:
            raise RuntimeError(f"HF Inference API error: {exc}") from exc

        text = ""
        if isinstance(data, list) and data:
            text = data[0].get("generated_text", "")
        elif isinstance(data, dict):
            text = data.get("generated_text", "")

        yield Token(text=text, logprob=None, finish_reason="stop")

    async def complete(self, prompt: str, *, max_tokens: int = 256, **kwargs):
        """Async generator yielding Token objects."""
        async for tok in self.chat([{"role": "user", "content": prompt}], max_tokens=max_tokens):
            yield tok

    async def close(self) -> None:
        pass
