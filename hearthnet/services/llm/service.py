"""M04 - LLM Service.

Spec: docs/M04-llm.md
Impl-ref: impl_ref.md §9

Backend priority (local-first):
  1. Ollama        - preferred zero-config
  2. llama.cpp     - local HTTP server
  3. OpenBMB/MiniCPM - lightweight local <8B
  4. Nemotron      - cloud or NIM
  5. OpenAI-compat - opt-in online fallback ONLY
  6. HF local      - local transformers
"""

from __future__ import annotations

from hearthnet.bus.capability import CapabilityDescriptor, RouteRequest
from hearthnet.services.llm.backends.base import BackendModel, ChatResult, LlmBackend


class LlmService:
    name = "llm"
    version = "1.0"

    def __init__(
        self,
        backends: list[LlmBackend] | None = None,
        model: str = "",
        requires_internet: bool = False,
    ) -> None:
        """
        backends: list of real LlmBackend instances (OllamaBackend, LlamaCppBackend, …)
                  If None or empty and model is non-empty, a legacy _EchoBackend is
                  used ONLY when model starts with 'demo-' or 'echo' (test contexts).
                  In all other cases an UnavailableBackend is registered so callers
                  get a clear error message instead of a silent echo.
        """
        self._backends: list[LlmBackend] = backends or []
        self._legacy_model = model
        self._legacy_requires_internet = requires_internet
        if not self._backends:
            if model.startswith("demo-") or model.startswith("echo"):
                # Allowed only for test scaffolding
                self._backends = [_EchoBackend(model, requires_internet)]
            else:
                # Production: register an unavailable backend that returns a useful error
                self._backends = [_UnavailableBackend()]

    def capabilities(self) -> list[tuple]:
        # Collect every (backend, model) pair across all configured backends.
        # The registry keys local capabilities by (node, name, version), so a
        # separate llm.chat per model would collide and only the last would
        # survive — making additional backends (e.g. sponsor clouds) unreachable.
        # Instead we register ONE llm.chat / llm.complete that advertises the
        # full model catalogue and dispatches to the owning backend by model.
        model_entries = [(backend, bm) for backend in self._backends for bm in backend.models]
        if not model_entries:
            return []
        _primary_backend, primary_bm = model_entries[0]
        model_names = [bm.name for _, bm in model_entries]
        params = {
            "model": primary_bm.name,
            "models": model_names,
            "requires_internet": primary_bm.requires_internet,
        }
        chat_descriptor = CapabilityDescriptor(
            name="llm.chat",
            version=(1, 0),
            stability="stable",
            params=dict(params),
            max_concurrent=2,
            trust_required="member",
            timeout_seconds=120,
            idempotent=False,
        )
        complete_descriptor = CapabilityDescriptor(
            name="llm.complete",
            version=(1, 0),
            stability="stable",
            params=dict(params),
            max_concurrent=2,
            trust_required="member",
            timeout_seconds=120,
            idempotent=False,
        )
        return [
            (chat_descriptor, self._handle_chat, _model_matches),
            (complete_descriptor, self._handle_complete, _model_matches),
        ]

    def _resolve_backend(self, model_name: str) -> tuple[LlmBackend, str]:
        """Pick the backend that serves ``model_name``; fall back to primary."""
        if model_name:
            for backend in self._backends:
                for bm in backend.models:
                    if bm.name == model_name:
                        return backend, model_name
        backend = self._backends[0]
        return backend, backend.models[0].name

    async def _handle_chat(self, req: RouteRequest) -> dict:
        inp = req.body.get("input", {})
        messages = inp.get("messages", [])
        params = req.body.get("params", {})
        backend, model_name = self._resolve_backend(str(params.get("model") or ""))
        temperature = float(params.get("temperature", 0.7))
        max_tokens = int(params.get("max_tokens", 1024))
        try:
            result = await backend.chat(
                messages,
                model=model_name,
                stream=False,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return {
                "output": {"message": {"role": "assistant", "content": result.text}},
                "meta": {
                    "model": result.model,
                    "tokens_in": result.tokens_in,
                    "tokens_out": result.tokens_out,
                    "ms": result.ms,
                },
            }
        except Exception as exc:
            return {"error": "internal_error", "message": str(exc)}

    async def _handle_complete(self, req: RouteRequest) -> dict:
        inp = req.body.get("input", {})
        prompt = inp.get("prompt", "")
        params = req.body.get("params", {})
        backend, model_name = self._resolve_backend(str(params.get("model") or ""))
        try:
            result = await backend.complete(prompt, model=model_name, stream=False)
            return {
                "output": {"text": result.text},
                "meta": {
                    "model": result.model,
                    "tokens_in": result.tokens_in,
                    "tokens_out": result.tokens_out,
                    "ms": result.ms,
                },
            }
        except Exception as exc:
            return {"error": "internal_error", "message": str(exc)}


class _UnavailableBackend:
    """Registered when no real LLM backend is configured.

    Returns a user-readable error message instead of silently echoing input.
    Instructs the operator to configure Ollama, llama.cpp, or another backend.
    """

    name = "unavailable"
    models = [
        BackendModel(
            name="unavailable",
            family="none",
            context_length=0,
            requires_internet=False,
        )
    ]

    def is_available(self) -> bool:
        return False

    async def warm(self) -> None:
        pass

    async def close(self) -> None:
        pass

    def health(self) -> dict:
        return {
            "status": "unavailable",
            "message": (
                "No LLM backend configured. "
                "Start Ollama (`ollama serve`) or configure llama.cpp / HF Transformers. "
                "See docs/HOWTO.md §6 for setup instructions."
            ),
        }

    async def chat(self, messages, *, model="", **kwargs) -> ChatResult:
        raise RuntimeError(
            "No LLM backend available. "
            "Configure Ollama, llama.cpp, OpenBMB or Nemotron in ~/.hearthnet/config.toml. "
            "See docs/HOWTO.md §6."
        )

    async def complete(self, prompt, *, model="", **kwargs) -> ChatResult:
        raise RuntimeError("No LLM backend available. See docs/HOWTO.md §6.")


class _EchoBackend:
    """FOR TESTS ONLY — never instantiated in production service paths.

    Use only in unit tests that need a deterministic response without a
    real model server.  LlmService raises RuntimeError when no real
    backend is provided in production.
    """

    name = "echo"

    def __init__(self, model: str = "echo", requires_internet: bool = False) -> None:
        self.models = [
            BackendModel(
                name=model,
                family="echo",
                context_length=4096,
                requires_internet=requires_internet,
            )
        ]

    def is_available(self) -> bool:
        return True  # always available for tests

    async def chat(
        self, messages, *, model="", stream=False, temperature=0.7, max_tokens=1024, **kwargs
    ) -> ChatResult:
        last = next(
            (m.get("content", "") for m in reversed(messages) if m.get("role") == "user"),
            "",
        )
        text = f"[{model or 'echo'}] {last}"
        return ChatResult(
            text=text,
            tokens_in=len(last.split()),
            tokens_out=len(text.split()),
            model=model or "echo",
            ms=1,
        )

    async def complete(self, prompt, *, model="", stream=False, **kwargs) -> ChatResult:
        return ChatResult(
            text=f"[{model or 'echo'}] {prompt}",
            tokens_in=len(prompt.split()),
            tokens_out=len(prompt.split()) + 1,
            model=model or "echo",
            ms=1,
        )

    async def warm(self) -> None:
        pass

    async def close(self) -> None:
        pass

    def health(self) -> dict:
        return {"status": "ok", "note": "echo-backend-tests-only"}

    async def warm(self) -> None:
        pass

    async def close(self) -> None:
        pass

    def health(self) -> dict:
        return {"backend": "echo", "status": "ok"}

    def is_available(self) -> bool:
        return True


def _model_matches(offered: dict, requested: dict) -> bool:
    req = requested.get("model")
    if not req:
        return True
    if req == offered.get("model"):
        return True
    return req in (offered.get("models") or [])
