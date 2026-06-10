"""M04 — OpenBMB / MiniCPM backend.

Spec: docs/M04-llm.md §3.2 / impl_ref.md §24
Supports OpenBMB MiniCPM family via:
  - vLLM, SGLang, or llama.cpp HTTP server (OpenAI-compatible)
  - Default endpoint: http://localhost:8000
  - Always local-first (requires_internet=False)

Small models (<8B) that run well on a Raspberry Pi 5 or modest laptop:
  - MiniCPM4-8B   (8B, fast, excellent instruction following)
  - MiniCPM3-4B   (4B, lighter, Pi-friendly)
  - MiniCPM-V-2_6 (8B + vision, for M20)

Config example (config.toml)::

    [[llm.backends]]
    name  = "openbmb"
    url   = "http://localhost:8000"
    model = "openbmb/MiniCPM4-8B"

    # OR multiple models via the same vLLM server:
    [[llm.backends]]
    name  = "openbmb"
    url   = "http://localhost:8000"
    # model omitted → all _OPENBMB_MODELS advertised
"""
from __future__ import annotations

from .openai_compat import OpenAICompatBackend
from .base import BackendModel

# Default MiniCPM model catalogue
_OPENBMB_MODELS: list[BackendModel] = [
    BackendModel(
        name="openbmb/MiniCPM4-8B",
        family="minicpm",
        context_length=32_768,
        requires_internet=False,
    ),
    BackendModel(
        name="openbmb/MiniCPM3-4B",
        family="minicpm",
        context_length=32_768,
        requires_internet=False,
    ),
    BackendModel(
        # Vision modality reserved for Phase 2 M20; advertised as text-only
        # until the vision envelope in CONTRACT lifts the restriction.
        name="openbmb/MiniCPM-V-2_6",
        family="minicpm",
        context_length=8_192,
        requires_internet=False,
    ),
]

# Small models for Raspberry Pi / low-RAM nodes
_LIGHTWEIGHT_MODELS: list[BackendModel] = [
    BackendModel(
        name="Qwen/Qwen2.5-3B-Instruct",
        family="qwen",
        context_length=32_768,
        requires_internet=False,
    ),
    BackendModel(
        name="microsoft/phi-4-mini",
        family="phi",
        context_length=16_384,
        requires_internet=False,
    ),
    BackendModel(
        name="google/gemma-3-4b-it",
        family="gemma",
        context_length=8_192,
        requires_internet=False,
    ),
]


class OpenBmbBackend(OpenAICompatBackend):
    """OpenBMB MiniCPM family served via vLLM / SGLang / llama.cpp.

    This is the recommended backend for local-first, low-power nodes such
    as a Raspberry Pi 5 (MiniCPM3-4B with llama.cpp) or a laptop (MiniCPM4-8B
    with Ollama or vLLM).
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        models: list[str] | None = None,
        api_key_env: str | None = None,
        *,
        include_lightweight: bool = False,
    ) -> None:
        if models:
            backend_models = [
                BackendModel(
                    name=m,
                    family="minicpm",
                    context_length=32_768,
                    requires_internet=False,
                )
                for m in models
            ]
        else:
            backend_models = list(_OPENBMB_MODELS)
            if include_lightweight:
                backend_models.extend(_LIGHTWEIGHT_MODELS)

        super().__init__(
            base_url=base_url,
            api_key_env=api_key_env or "OPENBMB_API_KEY",
            model=backend_models[0].name if backend_models else "openbmb/MiniCPM4-8B",
        )
        self.models = backend_models
        self.name = "openbmb"


class LightweightLocalBackend(OpenAICompatBackend):
    """Small <8B models for Raspberry Pi / edge nodes.

    Served by Ollama (``ollama serve``) or llama.cpp HTTP server.
    Default: http://localhost:11434 (Ollama).

    Models (all <8B, run on 4–8 GB RAM):
    - Qwen2.5-3B-Instruct
    - phi-4-mini
    - gemma-3-4b-it

    Config::

        [[llm.backends]]
        name  = "lightweight"
        url   = "http://localhost:11434/v1"   # Ollama v1 endpoint
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434/v1",
        models: list[str] | None = None,
        api_key_env: str | None = None,
    ) -> None:
        backend_models = (
            [
                BackendModel(
                    name=m,
                    family="local",
                    context_length=32_768,
                    requires_internet=False,
                )
                for m in models
            ]
            if models
            else list(_LIGHTWEIGHT_MODELS)
        )
        super().__init__(
            base_url=base_url,
            api_key_env=api_key_env or "LIGHTWEIGHT_API_KEY",
            model=backend_models[0].name if backend_models else "Qwen/Qwen2.5-3B-Instruct",
        )
        self.models = backend_models
        self.name = "lightweight"
