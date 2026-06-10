from __future__ import annotations

from dataclasses import dataclass
from typing import Any, AsyncIterator, Protocol


@dataclass(frozen=True)
class Token:
    text: str
    logprob: float = 0.0
    stop: bool = False


@dataclass(frozen=True)
class ChatResult:
    text: str
    tokens_in: int
    tokens_out: int
    model: str
    ms: int
    stop_reason: str = "stop"


@dataclass(frozen=True)
class BackendModel:
    name: str
    family: str  # "llama", "qwen", "mistral", etc.
    context_length: int
    requires_internet: bool


class LlmBackend(Protocol):
    name: str
    models: list[BackendModel]

    async def chat(
        self,
        messages: list[dict],
        *,
        model: str,
        stream: bool = False,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> ChatResult | AsyncIterator[Token]: ...

    async def complete(
        self,
        prompt: str,
        *,
        model: str,
        stream: bool = False,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> ChatResult | AsyncIterator[Token]: ...

    async def warm(self) -> None: ...
    async def close(self) -> None: ...
    def health(self) -> dict: ...
    def is_available(self) -> bool: ...
