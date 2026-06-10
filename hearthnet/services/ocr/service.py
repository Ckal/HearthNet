"""OcrService — registers ocr.image@1.0 and ocr.pdf@1.0 on the bus."""

from __future__ import annotations

import base64
from typing import Any


class OcrService:
    name = "ocr"
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
            from hearthnet.services.ocr.backends.tesseract import TesseractBackend

            b = TesseractBackend()
            if b.health().get("status") == "ok":
                backends.append(b)
        except Exception:
            pass
        try:
            from hearthnet.services.ocr.backends.trocr import TrocrBackend

            b = TrocrBackend()
            if b.health().get("status") == "ok":
                backends.append(b)
        except Exception:
            pass
        return backends

    def _select_backend(self, languages: list[str] | None, preferred: str | None) -> Any | None:
        """Return first healthy backend that supports the requested languages."""
        for backend in self._backends:
            if preferred and backend.name != preferred:
                continue
            h = backend.health()
            if h.get("status") != "ok":
                continue
            if languages:
                sup = set(backend.supported_languages)
                if not all(lang in sup for lang in languages):
                    continue
            return backend
        # Fallback: any healthy backend
        for backend in self._backends:
            if backend.health().get("status") == "ok":
                return backend
        return None

    # ── Capability registration ───────────────────────────────────────────────

    def register(self, bus: Any) -> None:
        from hearthnet.bus.capability import CapabilityDescriptor

        desc_image = CapabilityDescriptor(
            name="ocr.image",
            version=(1, 0),
            stability="stable",
            params={"backends": [b.name for b in self._backends]},
            max_concurrent=4,
            trust_required="member",
            timeout_seconds=60,
            idempotent=True,
        )
        desc_pdf = CapabilityDescriptor(
            name="ocr.pdf",
            version=(1, 0),
            stability="stable",
            params={"backends": [b.name for b in self._backends]},
            max_concurrent=2,
            trust_required="member",
            timeout_seconds=120,
            idempotent=True,
        )
        bus.register_capability(desc_image, self._handle_image, self.params_compatible)
        bus.register_capability(desc_pdf, self._handle_pdf, self.params_compatible)

    def params_compatible(self, offered: dict, requested: dict) -> bool:
        req_backend = requested.get("backend")
        if not req_backend:
            return True
        return req_backend in offered.get("backends", [])

    # ── Handlers ──────────────────────────────────────────────────────────────

    async def _handle_image(self, req: Any) -> dict:
        body = req.body if hasattr(req, "body") else req
        inp = body.get("input", body)
        image_cid: str | None = inp.get("image_cid")
        image_b64: str | None = inp.get("image_b64")
        languages: list[str] | None = inp.get("languages")
        preferred: str | None = inp.get("backend")

        image_bytes = self._resolve_bytes(image_cid, image_b64)
        if image_bytes is None:
            return {"error": "bad_request", "reason": "Provide image_cid or image_b64"}

        backend = self._select_backend(languages, preferred)
        if backend is None:
            return {
                "error": "backend_unavailable",
                "reason": "No healthy OCR backend available",
            }

        try:
            result = await backend.ocr_image(image_bytes, languages=languages)
        except Exception as exc:
            return {"error": "internal_error", "reason": str(exc)}

        return self._serialize_result(result)

    async def _handle_pdf(self, req: Any) -> dict:
        body = req.body if hasattr(req, "body") else req
        inp = body.get("input", body)
        pdf_cid: str | None = inp.get("pdf_cid")
        pdf_b64: str | None = inp.get("pdf_b64")
        pages: list[int] | None = inp.get("pages")
        languages: list[str] | None = inp.get("languages")
        preferred: str | None = inp.get("backend")

        pdf_bytes = self._resolve_bytes(pdf_cid, pdf_b64)
        if pdf_bytes is None:
            return {"error": "bad_request", "reason": "Provide pdf_cid or pdf_b64"}

        backend = self._select_backend(languages, preferred)
        if backend is None:
            return {
                "error": "backend_unavailable",
                "reason": "No healthy OCR backend available",
            }

        try:
            result = await backend.ocr_pdf(pdf_bytes, pages=pages, languages=languages)
        except Exception as exc:
            return {"error": "internal_error", "reason": str(exc)}

        return self._serialize_result(result)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _resolve_bytes(self, cid: str | None, b64: str | None) -> bytes | None:
        if b64:
            try:
                return base64.b64decode(b64)
            except Exception:
                return None
        if cid:
            # CID resolution requires blob store; left as integration point
            return None
        return None

    @staticmethod
    def _serialize_result(result: Any) -> dict:
        pages_out = []
        for page in result.pages:
            blocks_out = [
                {
                    "text": b.text,
                    "confidence": b.confidence,
                    "bbox": list(b.bbox) if b.bbox else None,
                    "language": b.language,
                }
                for b in page.blocks
            ]
            pages_out.append(
                {
                    "page": page.page,
                    "blocks": blocks_out,
                    "full_text": page.full_text,
                    "confidence_avg": page.confidence_avg,
                    "ms": page.ms,
                }
            )
        return {
            "pages": pages_out,
            "detected_languages": result.detected_languages,
            "backend": result.backend,
            "ms": result.ms,
        }
