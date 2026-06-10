"""Translation backend protocol and result types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class TranslationResult:
    text: str
    from_lang: str
    to_lang: str
    backend: str
    ms: int


@runtime_checkable
class TranslationBackend(Protocol):
    name: str
    supported_pairs: list[tuple[str, str]]

    async def translate(
        self,
        text: str,
        from_lang: str,
        to_lang: str,
        domain: str | None = None,
    ) -> TranslationResult: ...

    async def detect_language(self, text: str) -> str: ...

    def health(self) -> dict: ...
