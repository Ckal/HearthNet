"""SttService — registers stt.transcribe@1.0 on the bus."""
from __future__ import annotations

import base64
from typing import Any

from hearthnet.constants import STT_MAX_AUDIO_SECONDS


class SttService:
    name = "stt"
    version = "1.0"

    def __init__(
        self,
        backends: list[Any] | None = None,
        bus: Any = None,
    ) -> None:
        if backends is not None:
            self._backends = backends
        else:
            self._backends = self._discover_backends()
        if bus is not None:
            self.register(bus)

    # ── Backend discovery ─────────────────────────────────────────────────────

    def _discover_backends(self) -> list[Any]:
        backends: list[Any] = []
        try:
            from hearthnet.services.speech.backends.whisper_local import WhisperBackend
            b = WhisperBackend()
            if b.health().get("status") == "ok":
                backends.append(b)
        except Exception:
            pass
        return backends

    def _select_backend(self) -> Any | None:
        for backend in self._backends:
            if backend.health().get("status") == "ok":
                return backend
        return None

    # ── Capability registration ───────────────────────────────────────────────

    def register(self, bus: Any) -> None:
        from hearthnet.bus.capability import CapabilityDescriptor

        desc = CapabilityDescriptor(
            name="stt.transcribe",
            version=(1, 0),
            stability="stable",
            params={"backends": [b.name for b in self._backends]},
            max_concurrent=2,
            trust_required="member",
            timeout_seconds=STT_MAX_AUDIO_SECONDS + 30,
            idempotent=True,
        )
        bus.register_capability(desc, self._handle_transcribe, self.params_compatible)

    def params_compatible(self, offered: dict, requested: dict) -> bool:
        req_backend = requested.get("backend")
        if not req_backend:
            return True
        return req_backend in offered.get("backends", [])

    # ── Handler ───────────────────────────────────────────────────────────────

    async def _handle_transcribe(self, req: Any) -> dict:
        body = req.body if hasattr(req, "body") else req
        inp = body.get("input", body)

        audio_b64: str | None = inp.get("audio_b64")
        language: str | None = inp.get("language")
        translate_to_en: bool = bool(inp.get("translate_to_en", False))

        if not audio_b64:
            return {"error": "bad_request", "reason": "audio_b64 is required"}

        try:
            audio_bytes = base64.b64decode(audio_b64)
        except Exception:
            return {"error": "bad_request", "reason": "audio_b64 is not valid base64"}

        backend = self._select_backend()
        if backend is None:
            return {
                "error": "backend_unavailable",
                "reason": "No healthy STT backend available",
            }

        try:
            result = await backend.transcribe(
                audio_bytes, language=language, translate_to_en=translate_to_en
            )
        except Exception as exc:
            return {"error": "internal_error", "reason": str(exc)}

        segments_out = [
            {
                "start_seconds": s.start_seconds,
                "end_seconds": s.end_seconds,
                "text": s.text,
                "language": s.language,
                "confidence": s.confidence,
            }
            for s in result.segments
        ]
        return {
            "segments": segments_out,
            "full_text": result.full_text,
            "detected_language": result.detected_language,
            "backend": result.backend,
            "ms": result.ms,
        }
