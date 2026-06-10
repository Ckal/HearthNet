"""TtsService — registers tts.synthesize@1.0 on the bus."""

from __future__ import annotations

import base64
from typing import Any

from hearthnet.constants import TRANSLATION_MAX_CHARS


class TtsService:
    name = "tts"
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
            from hearthnet.services.speech.backends.edge_tts import EdgeTtsBackend

            b = EdgeTtsBackend()
            if b.health().get("status") == "ok":
                backends.append(b)
        except Exception:
            pass
        return backends

    def _select_backend(self, preferred: str | None = None) -> Any | None:
        for backend in self._backends:
            if preferred and backend.name != preferred:
                continue
            if backend.health().get("status") == "ok":
                return backend
        for backend in self._backends:
            if backend.health().get("status") == "ok":
                return backend
        return None

    # ── Capability registration ───────────────────────────────────────────────

    def register(self, bus: Any) -> None:
        from hearthnet.bus.capability import CapabilityDescriptor

        desc = CapabilityDescriptor(
            name="tts.synthesize",
            version=(1, 0),
            stability="stable",
            params={"backends": [b.name for b in self._backends]},
            max_concurrent=4,
            trust_required="member",
            timeout_seconds=60,
            idempotent=True,
        )
        bus.register_capability(desc, self._handle_synthesize, self.params_compatible)

    def params_compatible(self, offered: dict, requested: dict) -> bool:
        req_backend = requested.get("backend")
        if not req_backend:
            return True
        return req_backend in offered.get("backends", [])

    # ── Handler ───────────────────────────────────────────────────────────────

    async def _handle_synthesize(self, req: Any) -> dict:
        body = req.body if hasattr(req, "body") else req
        inp = body.get("input", body)

        text: str = inp.get("text", "")
        voice: str | None = inp.get("voice")
        language: str = inp.get("language", "de")
        fmt: str = inp.get("format", "ogg_vorbis")
        preferred: str | None = inp.get("backend")

        if not text:
            return {"error": "bad_request", "reason": "text is required"}

        if len(text) > TRANSLATION_MAX_CHARS:
            return {
                "error": "bad_request",
                "reason": f"Text too long: {len(text)} > {TRANSLATION_MAX_CHARS} chars",
            }

        backend = self._select_backend(preferred)
        if backend is None:
            return {
                "error": "backend_unavailable",
                "reason": "No healthy TTS backend available",
            }

        try:
            result = await backend.synthesize(text, voice=voice, language=language, format=fmt)
        except Exception as exc:
            return {"error": "internal_error", "reason": str(exc)}

        return {
            "audio_b64": base64.b64encode(result.audio_bytes).decode(),
            "audio_format": result.audio_format,
            "duration_seconds": result.duration_seconds,
            "backend": result.backend,
            "ms": result.ms,
        }
