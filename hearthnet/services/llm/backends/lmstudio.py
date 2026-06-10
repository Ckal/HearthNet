"""M04 — LmStudio OpenAI-compatible backend.

LM Studio serves a local OpenAI-compatible API on http://localhost:1234/v1.
Wraps OpenAICompatBackend with LM Studio defaults.
"""

from __future__ import annotations

from hearthnet.services.llm.backends.openai_compat import OpenAICompatBackend


class LmStudioBackend(OpenAICompatBackend):
    """LM Studio local inference server.

    Default endpoint: http://localhost:1234/v1
    LM Studio exposes whichever model is currently loaded; it is discovered
    dynamically via GET /v1/models on first availability check.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:1234/v1",
        model: str = "local-model",
        api_key_env: str = "",
    ) -> None:
        super().__init__(
            base_url=base_url,
            api_key_env=api_key_env,
            model=model,
        )

    @property
    def name(self) -> str:  # type: ignore[override]
        return "lmstudio"
