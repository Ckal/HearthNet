"""TrOCR backend via Hugging Face Transformers (optional dependency)."""
from __future__ import annotations

import asyncio
import io
import time
from typing import Any


class TrocrBackend:
    name = "trocr"

    def __init__(
        self,
        model: str = "microsoft/trocr-large-handwritten",
        device: str = "auto",
    ) -> None:
        self._model_name = model
        self._device = device
        self._processor: Any = None
        self._model: Any = None
        self._loaded = False

    @property
    def supported_languages(self) -> list[str]:
        # TrOCR is primarily English/handwriting; can be fine-tuned for others
        return ["eng", "deu"]

    def _resolve_device(self) -> str:
        if self._device != "auto":
            return self._device
        try:
            import torch
            return "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            return "cpu"

    def _load_model_sync(self) -> None:
        from transformers import TrOCRProcessor, VisionEncoderDecoderModel  # type: ignore[import]

        device = self._resolve_device()
        self._processor = TrOCRProcessor.from_pretrained(self._model_name)
        self._model = VisionEncoderDecoderModel.from_pretrained(self._model_name)
        self._model.to(device)
        self._loaded = True

    async def _ensure_loaded(self) -> None:
        if not self._loaded:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._load_model_sync)

    def health(self) -> dict:
        try:
            import transformers  # noqa: F401
        except ImportError:
            return {"backend": self.name, "status": "unavailable", "reason": "transformers not installed"}
        return {"backend": self.name, "status": "ok", "model": self._model_name}

    def _run_trocr_sync(self, image_bytes: bytes) -> tuple[str, float]:
        from PIL import Image  # type: ignore[import]
        import torch

        device = self._resolve_device()
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        pixel_values = self._processor(images=image, return_tensors="pt").pixel_values.to(device)
        with torch.no_grad():
            generated_ids = self._model.generate(pixel_values)
        text = self._processor.batch_decode(generated_ids, skip_special_tokens=True)[0]
        return text, 1.0

    async def ocr_image(
        self,
        image_bytes: bytes,
        languages: list[str] | None = None,
    ) -> Any:
        from hearthnet.services.ocr.backends.base import OcrBlock, OcrPageResult, OcrResult

        await self._ensure_loaded()
        t0 = time.monotonic()
        loop = asyncio.get_event_loop()
        text, confidence = await loop.run_in_executor(None, self._run_trocr_sync, image_bytes)
        ms = int((time.monotonic() - t0) * 1000)

        block = OcrBlock(text=text, confidence=confidence, bbox=None, language=None)
        page = OcrPageResult(
            page=1, blocks=[block], full_text=text, confidence_avg=confidence, ms=ms
        )
        return OcrResult(pages=[page], detected_languages=[], backend=self.name, ms=ms)

    async def ocr_pdf(
        self,
        pdf_bytes: bytes,
        pages: list[int] | None = None,
        languages: list[str] | None = None,
    ) -> Any:
        from hearthnet.services.ocr.backends.base import OcrResult

        try:
            from pdf2image import convert_from_bytes  # type: ignore[import]
        except ImportError:
            from hearthnet.services.ocr.backends.base import OcrBlock, OcrPageResult

            return OcrResult(
                pages=[OcrPageResult(page=1, blocks=[], full_text="", confidence_avg=0.0, ms=0)],
                detected_languages=[],
                backend=self.name,
                ms=0,
            )

        t0 = time.monotonic()
        images = convert_from_bytes(pdf_bytes, dpi=200)
        page_results = []
        for idx, img in enumerate(images, start=1):
            if pages and idx not in pages:
                continue
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            partial = await self.ocr_image(buf.getvalue(), languages)
            from hearthnet.services.ocr.backends.base import OcrPageResult

            old = partial.pages[0]
            page_results.append(
                OcrPageResult(
                    page=idx,
                    blocks=old.blocks,
                    full_text=old.full_text,
                    confidence_avg=old.confidence_avg,
                    ms=old.ms,
                )
            )
        ms = int((time.monotonic() - t0) * 1000)
        return OcrResult(pages=page_results, detected_languages=[], backend=self.name, ms=ms)
