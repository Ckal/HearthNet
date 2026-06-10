"""OCR backend protocol and result types."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class OcrBlock:
    text: str
    confidence: float
    bbox: tuple[int, int, int, int] | None = None
    language: str | None = None


@dataclass(frozen=True)
class OcrPageResult:
    page: int
    blocks: list[OcrBlock]
    full_text: str
    confidence_avg: float
    ms: int


@dataclass(frozen=True)
class OcrResult:
    pages: list[OcrPageResult]
    detected_languages: list[str]
    backend: str
    ms: int


@runtime_checkable
class OcrBackend(Protocol):
    name: str
    supported_languages: list[str]

    async def ocr_image(
        self,
        image_bytes: bytes,
        languages: list[str] | None = None,
    ) -> OcrResult: ...

    async def ocr_pdf(
        self,
        pdf_bytes: bytes,
        pages: list[int] | None = None,
        languages: list[str] | None = None,
    ) -> OcrResult: ...

    def health(self) -> dict: ...
