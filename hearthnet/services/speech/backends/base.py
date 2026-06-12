"""STT and TTS backend protocol and result types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

# ── STT ───────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SttSegment:
    start_seconds: float
    end_seconds: float
    text: str
    language: str | None = None
    confidence: float | None = None


@dataclass(frozen=True)
class SttResult:
    segments: list[SttSegment]
    full_text: str
    detected_language: str
    backend: str
    ms: int


@runtime_checkable
class SttBackend(Protocol):
    name: str

    async def transcribe(
        self,
        audio_bytes: bytes,
        language: str | None = None,
        translate_to_en: bool = False,
    ) -> SttResult: ...

    def health(self) -> dict: ...


# ── TTS ───────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TtsResult:
    audio_bytes: bytes
    audio_format: str
    duration_seconds: float
    backend: str
    ms: int


@runtime_checkable
class TtsBackend(Protocol):
    name: str

    async def synthesize(
        self,
        text: str,
        voice: str | None = None,
        language: str = "de",
        audio_format: str = "ogg_vorbis",
    ) -> TtsResult: ...

    def health(self) -> dict: ...
