"""M04 — Modal.com inference backend.

Spec: docs/M04-llm.md §3.2
Supports running LLM inference on Modal serverless GPU compute.

Two usage patterns:
  1. Remote call to a deployed Modal endpoint (MODAL_ENDPOINT env var)
  2. Direct Modal SDK invocation (requires modal[all] installed + auth)

Configure in config.toml::

    [[llm.backends]]
    name = "modal"
    endpoint = "https://your-org--hearthnet-llm.modal.run"
    model = "meta-llama/Llama-3.2-3B-Instruct"

Or via environment::

    MODAL_ENDPOINT=https://your-org--hearthnet-llm.modal.run
    MODAL_MODEL=meta-llama/Llama-3.2-3B-Instruct

Qualifies for: Modal Best Use Of Modal prize ($10k credits).
See: https://modal.com/docs/guide/webhooks
"""

from __future__ import annotations

import os
import time

from .base import BackendModel, ChatResult

_MODAL_DEFAULT_MODELS: list[BackendModel] = [
    BackendModel(
        name="meta-llama/Llama-3.2-3B-Instruct",
        family="llama",
        context_length=128_000,
        requires_internet=True,
    ),
    BackendModel(
        name="HuggingFaceTB/SmolLM2-1.7B-Instruct",
        family="smollm",
        context_length=8_192,
        requires_internet=True,
    ),
]


class ModalBackend:
    """Modal serverless GPU backend.

    Calls a Modal web endpoint that exposes an OpenAI-compatible /chat/completions API.
    The endpoint can be generated from the included ``scripts/modal_deploy.py``.
    """

    name = "modal"

    def __init__(
        self,
        endpoint: str | None = None,
        model: str | None = None,
        api_token: str | None = None,
    ) -> None:
        self._endpoint = (
            (endpoint or os.getenv("MODAL_ENDPOINT", "")).rstrip("/")
        )
        self._model = model or os.getenv(
            "MODAL_MODEL", "HuggingFaceTB/SmolLM2-1.7B-Instruct"
        )
        self._token = api_token or os.getenv("MODAL_TOKEN", "")
        self.models: list[BackendModel] = []

    # ------------------------------------------------------------------
    def is_available(self) -> bool:
        if not self._endpoint:
            return False
        try:
            import httpx

            resp = httpx.get(f"{self._endpoint}/health", timeout=5.0)
            return resp.status_code == 200
        except Exception:
            return False

    async def warm(self) -> None:
        # Report the configured model
        self.models = [
            BackendModel(
                name=self._model,
                family="modal",
                context_length=128_000,
                requires_internet=True,
            )
        ]

    async def close(self) -> None:
        pass

    # ------------------------------------------------------------------
    async def chat(
        self,
        messages: list[dict],
        *,
        model: str = "",
        stream: bool = False,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        **kwargs,
    ) -> ChatResult:
        import httpx

        model = model or self._model
        t0 = time.monotonic()

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{self._endpoint}/v1/chat/completions",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()

        choice = data["choices"][0]
        text = choice["message"]["content"]
        usage = data.get("usage", {})
        ms = int((time.monotonic() - t0) * 1000)

        return ChatResult(
            text=text,
            tokens_in=usage.get("prompt_tokens", 0),
            tokens_out=usage.get("completion_tokens", 0),
            model=model,
            ms=ms,
            stop_reason=choice.get("finish_reason", "stop"),
        )

    async def complete(
        self,
        prompt: str,
        *,
        model: str = "",
        stream: bool = False,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        **kwargs,
    ) -> ChatResult:
        return await self.chat(
            [{"role": "user", "content": prompt}],
            model=model,
            stream=stream,
            temperature=temperature,
            max_tokens=max_tokens,
        )
