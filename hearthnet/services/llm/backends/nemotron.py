"""M04 — Nemotron LLM backend.

Spec: docs/M04-llm.md §3.2 / impl_ref.md §24
Supports NVIDIA Nemotron models via:
  - Cloud: integrate.api.nvidia.com/v1 (OpenAI-compat, requires_internet=True)
  - Local: self-hosted NIM / vLLM endpoint (requires_internet=False)

Registered by LlmService when 'nemotron' backend is configured in config.toml.
Deregistered automatically by M09 Detector when offline (requires_internet=True models).
"""
from __future__ import annotations

from .openai_compat import OpenAICompatBackend
from .base import BackendModel

# Default cloud-hosted Nemotron models
_NEMOTRON_CLOUD_MODELS: list[BackendModel] = [
    BackendModel(
        name="nvidia/llama-3.1-nemotron-70b-instruct",
        family="llama",
        context_length=128_000,
        requires_internet=True,
    ),
    BackendModel(
        name="nvidia/nemotron-mini-4b-instruct",
        family="nemotron",
        context_length=4_096,
        requires_internet=True,
    ),
    BackendModel(
        name="nvidia/llama-3.3-nemotron-super-49b-v1",
        family="llama",
        context_length=128_000,
        requires_internet=True,
    ),
]


class NemotronBackend(OpenAICompatBackend):
    """NVIDIA Nemotron via NVIDIA NIM (cloud or self-hosted).

    Config example (config.toml)::

        [[llm.backends]]
        name = "nemotron"
        url  = "https://integrate.api.nvidia.com/v1"   # or local NIM endpoint
        model = "nvidia/llama-3.1-nemotron-70b-instruct"
        api_key_env = "NVIDIA_API_KEY"

    The ``model`` key is optional; if omitted all default Nemotron models are
    advertised (cloud URLs) or the single locally-served model (local URL).
    """

    def __init__(
        self,
        base_url: str = "https://integrate.api.nvidia.com/v1",
        models: list[str] | None = None,
        api_key_env: str = "NVIDIA_API_KEY",
        *,
        local: bool = False,
    ) -> None:
        is_local = local or "localhost" in base_url or "127.0.0.1" in base_url

        if models:
            backend_models = [
                BackendModel(
                    name=m,
                    family="nemotron",
                    context_length=128_000,
                    requires_internet=not is_local,
                )
                for m in models
            ]
        else:
            if is_local:
                # Local NIM — single generic entry; override with actual model at runtime
                backend_models = [
                    BackendModel(
                        name="nemotron-local",
                        family="nemotron",
                        context_length=128_000,
                        requires_internet=False,
                    )
                ]
            else:
                backend_models = _NEMOTRON_CLOUD_MODELS

        super().__init__(
            base_url=base_url,
            api_key_env=api_key_env or "NVIDIA_API_KEY",
            model=backend_models[0].name if backend_models else "nvidia/nemotron-mini-4b-instruct",
        )
        # Override the single-model list with the full catalogue
        self.models = backend_models
        self.name = "nemotron"
