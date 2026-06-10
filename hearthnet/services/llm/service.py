from __future__ import annotations

from hearthnet.bus.capability import CapabilityDescriptor, RouteRequest
from hearthnet.services.llm.backends.base import BackendModel, ChatResult, LlmBackend


class LlmService:
    name = "llm"
    version = "1.0"

    def __init__(
        self,
        backends: list[LlmBackend] | None = None,
        model: str = "demo-local",
        requires_internet: bool = False,
    ) -> None:
        """Legacy constructor compat: if backends is None, use a simple echo backend."""
        self._backends: list[LlmBackend] = backends or []
        self._legacy_model = model
        self._legacy_requires_internet = requires_internet
        if not self._backends:
            self._backends = [_EchoBackend(model, requires_internet)]

    def capabilities(self) -> list[tuple]:
        result = []
        for backend in self._backends:
            for bm in backend.models:
                descriptor = CapabilityDescriptor(
                    name="llm.chat",
                    version=(1, 0),
                    stability="stable",
                    params={"model": bm.name, "requires_internet": bm.requires_internet},
                    max_concurrent=2,
                    trust_required="member",
                    timeout_seconds=120,
                    idempotent=False,
                )
                result.append(
                    (descriptor, self._make_chat_handler(backend, bm.name), _model_matches)
                )
                descriptor_complete = CapabilityDescriptor(
                    name="llm.complete",
                    version=(1, 0),
                    stability="stable",
                    params={"model": bm.name, "requires_internet": bm.requires_internet},
                    max_concurrent=2,
                    trust_required="member",
                    timeout_seconds=120,
                    idempotent=False,
                )
                result.append(
                    (
                        descriptor_complete,
                        self._make_complete_handler(backend, bm.name),
                        _model_matches,
                    )
                )
        return result

    def _make_chat_handler(self, backend: LlmBackend, model_name: str):
        async def handle_chat(req: RouteRequest) -> dict:
            inp = req.body.get("input", {})
            messages = inp.get("messages", [])
            params = req.body.get("params", {})
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
                    "output": {
                        "message": {"role": "assistant", "content": result.text}
                    },
                    "meta": {
                        "model": result.model,
                        "tokens_in": result.tokens_in,
                        "tokens_out": result.tokens_out,
                        "ms": result.ms,
                    },
                }
            except Exception as exc:
                return {"error": "internal_error", "message": str(exc)}

        return handle_chat

    def _make_complete_handler(self, backend: LlmBackend, model_name: str):
        async def handle_complete(req: RouteRequest) -> dict:
            inp = req.body.get("input", {})
            prompt = inp.get("prompt", "")
            params = req.body.get("params", {})
            try:
                result = await backend.complete(
                    prompt, model=model_name, stream=False
                )
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

        return handle_complete


class _EchoBackend:
    """Fallback echo backend for demo/testing."""

    name = "echo"

    def __init__(self, model: str = "demo-local", requires_internet: bool = False) -> None:
        self.models = [
            BackendModel(
                name=model,
                family="echo",
                context_length=4096,
                requires_internet=requires_internet,
            )
        ]

    async def chat(
        self, messages, *, model="", stream=False, temperature=0.7, max_tokens=1024, **kwargs
    ) -> ChatResult:
        last = next(
            (
                m.get("content", "")
                for m in reversed(messages)
                if m.get("role") == "user"
            ),
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
        return {"backend": "echo", "status": "ok"}

    def is_available(self) -> bool:
        return True


def _model_matches(offered: dict, requested: dict) -> bool:
    return not requested.get("model") or requested.get("model") == offered.get("model")
