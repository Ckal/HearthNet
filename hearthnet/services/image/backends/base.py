from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ImageDescription:
    caption: str
    tags: list[str]
    objects: list[str]
    ocr_text: str | None
    backend: str
    ms: int


@dataclass(frozen=True)
class GenerationResult:
    image_bytes: bytes
    width: int
    height: int
    prompt_used: str
    backend: str
    ms: int


@runtime_checkable
class ImageDescribeBackend(Protocol):
    name: str

    async def describe(
        self,
        image_bytes: bytes,
        mode: str = "caption",
    ) -> ImageDescription: ...

    def health(self) -> dict: ...


@runtime_checkable
class ImageGenerateBackend(Protocol):
    name: str

    async def generate(
        self,
        prompt: str,
        width: int = 512,
        height: int = 512,
        steps: int = 20,
        lora: str | None = None,
    ) -> GenerationResult: ...

    def health(self) -> dict: ...
