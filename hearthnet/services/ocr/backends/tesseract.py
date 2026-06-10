"""Tesseract OCR backend via pytesseract (optional dependency)."""
from __future__ import annotations

import asyncio
import io
import subprocess
import time
from typing import Any


class TesseractBackend:
    name = "tesseract"

    def __init__(
        self,
        min_confidence: float = 0.5,
        data_dir: str | None = None,
    ) -> None:
        self._min_confidence = min_confidence
        self._data_dir = data_dir
        self._supported_languages: list[str] | None = None

    @property
    def supported_languages(self) -> list[str]:
        if self._supported_languages is None:
            self._supported_languages = self._read_langs()
        return self._supported_languages

    def _read_langs(self) -> list[str]:
        try:
            result = subprocess.run(
                ["tesseract", "--list-langs"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            lines = (result.stdout + result.stderr).splitlines()
            # Output starts with "List of available tessdata languages..." then one lang per line
            return [ln.strip() for ln in lines if ln.strip() and not ln.startswith("List")]
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            return []

    def health(self) -> dict:
        try:
            import pytesseract  # noqa: F401
        except ImportError:
            return {"backend": self.name, "status": "unavailable", "reason": "pytesseract not installed"}

        try:
            subprocess.run(["tesseract", "--version"], capture_output=True, timeout=5, check=True)
        except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
            return {"backend": self.name, "status": "unavailable", "reason": "tesseract binary not found"}

        return {"backend": self.name, "status": "ok", "languages": len(self.supported_languages)}

    async def ocr_image(
        self,
        image_bytes: bytes,
        languages: list[str] | None = None,
    ) -> Any:
        from hearthnet.services.ocr.backends.base import OcrBlock, OcrPageResult, OcrResult

        t0 = time.monotonic()
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, self._ocr_image_sync, image_bytes, languages)
        ms = int((time.monotonic() - t0) * 1000)
        result.pages[0] = OcrPageResult(
            page=result.pages[0].page,
            blocks=result.pages[0].blocks,
            full_text=result.pages[0].full_text,
            confidence_avg=result.pages[0].confidence_avg,
            ms=ms,
        )
        return OcrResult(
            pages=result.pages,
            detected_languages=result.detected_languages,
            backend=self.name,
            ms=ms,
        )

    def _ocr_image_sync(self, image_bytes: bytes, languages: list[str] | None) -> Any:
        from hearthnet.services.ocr.backends.base import OcrBlock, OcrPageResult, OcrResult

        try:
            import pytesseract
            from PIL import Image
        except ImportError as e:
            raise RuntimeError(f"pytesseract/Pillow not installed: {e}") from e

        t0 = time.monotonic()
        image = Image.open(io.BytesIO(image_bytes))

        kwargs: dict = {}
        if self._data_dir:
            kwargs["config"] = f"--tessdata-dir {self._data_dir}"
        lang_str = "+".join(languages) if languages else None
        if lang_str:
            kwargs["lang"] = lang_str

        data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT, **kwargs)

        blocks: list[OcrBlock] = []
        full_text_parts: list[str] = []
        confidences: list[float] = []
        detected_langs: list[str] = []

        n = len(data["text"])
        for i in range(n):
            word = str(data["text"][i]).strip()
            if not word:
                continue
            conf_raw = data["conf"][i]
            conf = float(conf_raw) / 100.0 if conf_raw != -1 else 0.0
            if conf < self._min_confidence and conf_raw != -1:
                continue
            x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
            blocks.append(OcrBlock(text=word, confidence=conf, bbox=(x, y, w, h), language=None))
            full_text_parts.append(word)
            if conf_raw != -1:
                confidences.append(conf)

        full_text = " ".join(full_text_parts)
        confidence_avg = sum(confidences) / len(confidences) if confidences else 0.0
        ms = int((time.monotonic() - t0) * 1000)

        page = OcrPageResult(
            page=1,
            blocks=blocks,
            full_text=full_text,
            confidence_avg=confidence_avg,
            ms=ms,
        )
        return OcrResult(pages=[page], detected_languages=detected_langs, backend=self.name, ms=ms)

    async def ocr_pdf(
        self,
        pdf_bytes: bytes,
        pages: list[int] | None = None,
        languages: list[str] | None = None,
    ) -> Any:
        from hearthnet.services.ocr.backends.base import OcrResult

        t0 = time.monotonic()
        loop = asyncio.get_event_loop()
        result_pages = await loop.run_in_executor(
            None, self._ocr_pdf_sync, pdf_bytes, pages, languages
        )
        ms = int((time.monotonic() - t0) * 1000)
        all_langs: list[str] = []
        for p in result_pages:
            all_langs.extend(p.detected_languages)
        return OcrResult(
            pages=[p.pages[0] for p in result_pages],
            detected_languages=list(dict.fromkeys(all_langs)),
            backend=self.name,
            ms=ms,
        )

    def _ocr_pdf_sync(
        self, pdf_bytes: bytes, pages: list[int] | None, languages: list[str] | None
    ) -> list[Any]:
        """Convert PDF pages to images via pdf2image, then OCR each."""
        try:
            from pdf2image import convert_from_bytes
        except ImportError:
            # Fallback: try pypdf text extraction (no image OCR)
            return self._ocr_pdf_pypdf(pdf_bytes, pages)

        images = convert_from_bytes(pdf_bytes, dpi=200)
        results = []
        for idx, img in enumerate(images, start=1):
            if pages and idx not in pages:
                continue
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            r = self._ocr_image_sync(buf.getvalue(), languages)
            # Re-tag page number
            from hearthnet.services.ocr.backends.base import OcrPageResult

            old_page = r.pages[0]
            new_page = OcrPageResult(
                page=idx,
                blocks=old_page.blocks,
                full_text=old_page.full_text,
                confidence_avg=old_page.confidence_avg,
                ms=old_page.ms,
            )
            from hearthnet.services.ocr.backends.base import OcrResult

            results.append(OcrResult(pages=[new_page], detected_languages=[], backend=self.name, ms=0))
        return results

    def _ocr_pdf_pypdf(self, pdf_bytes: bytes, pages: list[int] | None) -> list[Any]:
        """Best-effort text extraction from PDF using pypdf (no image rendering)."""
        try:
            import pypdf
        except ImportError:
            raise RuntimeError("Neither pdf2image nor pypdf is installed") from None

        from hearthnet.services.ocr.backends.base import OcrBlock, OcrPageResult, OcrResult

        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        results = []
        for idx, pdf_page in enumerate(reader.pages, start=1):
            if pages and idx not in pages:
                continue
            text = pdf_page.extract_text() or ""
            block = OcrBlock(text=text, confidence=1.0, bbox=None, language=None)
            page_result = OcrPageResult(
                page=idx, blocks=[block], full_text=text, confidence_avg=1.0, ms=0
            )
            results.append(
                OcrResult(pages=[page_result], detected_languages=[], backend=self.name, ms=0)
            )
        return results
