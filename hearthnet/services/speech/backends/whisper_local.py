"""Whisper local STT backend (openai-whisper or faster-whisper)."""

from __future__ import annotations

import asyncio
import tempfile
import time
from typing import Any


class WhisperBackend:
    name = "whisper"

    def __init__(
        self,
        model_size: str = "base",
        device: str = "auto",
    ) -> None:
        self._model_size = model_size
        self._device = device
        self._model: Any = None
        self._backend_lib: str | None = None  # "openai_whisper" or "faster_whisper"

    def _resolve_device(self) -> str:
        if self._device != "auto":
            return self._device
        try:
            import torch

            return "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            return "cpu"

    def health(self) -> dict:
        # Prefer faster_whisper, fall back to openai whisper
        try:
            import faster_whisper  # noqa: F401

            return {
                "backend": self.name,
                "status": "ok",
                "lib": "faster_whisper",
                "model": self._model_size,
            }
        except ImportError:
            pass
        try:
            import whisper  # noqa: F401

            return {
                "backend": self.name,
                "status": "ok",
                "lib": "openai_whisper",
                "model": self._model_size,
            }
        except ImportError:
            pass
        return {
            "backend": self.name,
            "status": "unavailable",
            "reason": "Neither openai-whisper nor faster-whisper is installed",
        }

    def _load_model_sync(self) -> None:
        device = self._resolve_device()
        try:
            from faster_whisper import WhisperModel  # type: ignore[import]

            self._model = WhisperModel(self._model_size, device=device)
            self._backend_lib = "faster_whisper"
            return
        except ImportError:
            pass
        import whisper  # type: ignore[import]

        self._model = whisper.load_model(self._model_size, device=device)
        self._backend_lib = "openai_whisper"

    async def _ensure_loaded(self) -> None:
        if self._model is None:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._load_model_sync)

    async def transcribe(
        self,
        audio_bytes: bytes,
        language: str | None = None,
        translate_to_en: bool = False,
    ) -> Any:
        from hearthnet.services.speech.backends.base import SttResult

        await self._ensure_loaded()
        t0 = time.monotonic()

        loop = asyncio.get_event_loop()
        segments, detected_lang = await loop.run_in_executor(
            None, self._transcribe_sync, audio_bytes, language, translate_to_en
        )
        ms = int((time.monotonic() - t0) * 1000)
        full_text = " ".join(s.text for s in segments)
        return SttResult(
            segments=segments,
            full_text=full_text,
            detected_language=detected_lang or "unknown",
            backend=self.name,
            ms=ms,
        )

    def _transcribe_sync(
        self,
        audio_bytes: bytes,
        language: str | None,
        translate_to_en: bool,
    ) -> tuple[list[Any], str | None]:
        from hearthnet.services.speech.backends.base import SttSegment

        # Write to temp file because whisper expects file path
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        segments_out: list[SttSegment] = []
        detected: str | None = None

        try:
            if self._backend_lib == "faster_whisper":
                task = "translate" if translate_to_en else "transcribe"
                segs, info = self._model.transcribe(
                    tmp_path,
                    language=language,
                    task=task,
                )
                detected = info.language
                for seg in segs:
                    segments_out.append(
                        SttSegment(
                            start_seconds=seg.start,
                            end_seconds=seg.end,
                            text=seg.text.strip(),
                            language=detected,
                            confidence=None,
                        )
                    )
            else:
                # openai-whisper
                task = "translate" if translate_to_en else "transcribe"
                kwargs: dict = {"task": task}
                if language:
                    kwargs["language"] = language
                result = self._model.transcribe(tmp_path, **kwargs)
                detected = result.get("language")
                for seg in result.get("segments", []):
                    segments_out.append(
                        SttSegment(
                            start_seconds=float(seg["start"]),
                            end_seconds=float(seg["end"]),
                            text=str(seg["text"]).strip(),
                            language=detected,
                            confidence=None,
                        )
                    )
        finally:
            import os

            try:
                os.unlink(tmp_path)
            except OSError:
                pass

        return segments_out, detected
