"""TranslationService — registers trans.text@1.0 on the bus."""
from __future__ import annotations

from typing import Any

from hearthnet.constants import TRANSLATION_MAX_CHARS


class TranslationService:
    name = "translation"
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
            from hearthnet.services.translation.backends.nllb import NllbBackend
            b = NllbBackend()
            if b.health().get("status") == "ok":
                backends.append(b)
        except Exception:
            pass
        return backends

    def _select_backend(
        self,
        from_lang: str,
        to_lang: str,
        preferred: str | None = None,
    ) -> Any | None:
        for backend in self._backends:
            if preferred and backend.name != preferred:
                continue
            if backend.health().get("status") != "ok":
                continue
            pairs = backend.supported_pairs
            if from_lang == "auto" or (from_lang, to_lang) in pairs:
                return backend
        # Any healthy backend as fallback
        for backend in self._backends:
            if backend.health().get("status") == "ok":
                return backend
        return None

    # ── Capability registration ───────────────────────────────────────────────

    def register(self, bus: Any) -> None:
        from hearthnet.bus.capability import CapabilityDescriptor

        desc = CapabilityDescriptor(
            name="trans.text",
            version=(1, 0),
            stability="stable",
            params={"backends": [b.name for b in self._backends], "max_chars": TRANSLATION_MAX_CHARS},
            max_concurrent=4,
            trust_required="member",
            timeout_seconds=30,
            idempotent=True,
        )
        bus.register_capability(desc, self._handle_translate, self.params_compatible)

    def params_compatible(self, offered: dict, requested: dict) -> bool:
        req_backend = requested.get("backend")
        if not req_backend:
            return True
        return req_backend in offered.get("backends", [])

    # ── Handler ───────────────────────────────────────────────────────────────

    async def _handle_translate(self, req: Any) -> dict:
        body = req.body if hasattr(req, "body") else req
        inp = body.get("input", body)

        text: str = inp.get("text", "")
        from_lang: str = inp.get("from_lang", "auto")
        to_lang: str | None = inp.get("to_lang")
        domain: str | None = inp.get("domain")
        preferred: str | None = inp.get("backend")

        if not to_lang:
            return {"error": "bad_request", "reason": "to_lang is required"}

        if len(text) > TRANSLATION_MAX_CHARS:
            return {
                "error": "bad_request",
                "reason": f"Text too long: {len(text)} > {TRANSLATION_MAX_CHARS} chars",
            }

        backend = self._select_backend(from_lang, to_lang, preferred)
        if backend is None:
            return {
                "error": "backend_unavailable",
                "reason": "No healthy translation backend available",
            }

        try:
            result = await backend.translate(text, from_lang=from_lang, to_lang=to_lang, domain=domain)
        except Exception as exc:
            return {"error": "internal_error", "reason": str(exc)}

        return {
            "text": result.text,
            "from_lang": result.from_lang,
            "to_lang": result.to_lang,
            "backend": result.backend,
            "ms": result.ms,
        }
