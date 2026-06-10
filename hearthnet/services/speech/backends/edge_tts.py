"""Edge TTS backend (Microsoft Edge text-to-speech via edge-tts package)."""

from __future__ import annotations

import io
import time
from typing import Any

from hearthnet.constants import STT_MAX_AUDIO_SECONDS


class EdgeTtsBackend:
    name = "edge_tts"
    requires_internet = True

    def __init__(self) -> None:
        pass

    def health(self) -> dict:
        try:
            import edge_tts  # noqa: F401

            return {"backend": self.name, "status": "ok", "requires_internet": True}
        except ImportError:
            return {
                "backend": self.name,
                "status": "unavailable",
                "reason": "edge-tts not installed",
            }

    async def synthesize(
        self,
        text: str,
        voice: str | None = "de-DE-KatjaNeural",
        language: str = "de",
        format: str = "ogg_vorbis",
    ) -> Any:
        from hearthnet.services.speech.backends.base import TtsResult

        try:
            import edge_tts  # type: ignore[import]
        except ImportError:
            raise RuntimeError("edge-tts not installed") from None

        selected_voice = voice or _default_voice(language)
        t0 = time.monotonic()

        communicate = edge_tts.Communicate(text, selected_voice)
        buf = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                buf.write(chunk["data"])

        audio_bytes = buf.getvalue()
        ms = int((time.monotonic() - t0) * 1000)

        # Estimate duration from audio length (rough: ~32kbps ogg)
        duration_seconds = min(
            len(audio_bytes) / (32 * 1024 / 8),
            float(STT_MAX_AUDIO_SECONDS),
        )

        # edge-tts natively outputs mp3; wrap in chosen format label
        return TtsResult(
            audio_bytes=audio_bytes,
            audio_format="mp3",  # edge-tts always outputs mp3
            duration_seconds=duration_seconds,
            backend=self.name,
            ms=ms,
        )


def _default_voice(language: str) -> str:
    _VOICES: dict[str, str] = {
        "de": "de-DE-KatjaNeural",
        "en": "en-US-JennyNeural",
        "fr": "fr-FR-DeniseNeural",
        "es": "es-ES-ElviraNeural",
        "it": "it-IT-ElsaNeural",
        "nl": "nl-NL-ColetteNeural",
        "pl": "pl-PL-ZofiaNeural",
        "ru": "ru-RU-SvetlanaNeural",
        "uk": "uk-UA-PolinaNeural",
        "ar": "ar-SA-ZariyahNeural",
        "tr": "tr-TR-EmelNeural",
    }
    return _VOICES.get(language, "en-US-JennyNeural")
