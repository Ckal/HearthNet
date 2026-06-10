from __future__ import annotations

import time
from typing import TYPE_CHECKING

from hearthnet.services.image.backends.base import ImageDescription, GenerationResult

if TYPE_CHECKING:
    pass

_TASK_MAP = {
    "caption": "<CAPTION>",
    "detailed_caption": "<DETAILED_CAPTION>",
    "ocr": "<OCR>",
    "object_detection": "<OD>",
}


class Florence2Backend:
    """Vision backend using Microsoft Florence-2."""

    name = "florence2"

    def __init__(
        self,
        model: str = "microsoft/Florence-2-large",
        device: str = "auto",
    ) -> None:
        self._model_id = model
        self._device = device
        self._processor = None
        self._model = None
        self._loaded = False
        self._load_error: str | None = None

    def _load(self) -> bool:
        if self._loaded:
            return True
        if self._load_error:
            return False
        try:
            from transformers import AutoProcessor, AutoModelForCausalLM  # type: ignore[import-untyped]
            import torch  # type: ignore[import-untyped]

            device = self._device
            if device == "auto":
                device = "cuda" if torch.cuda.is_available() else "cpu"

            self._processor = AutoProcessor.from_pretrained(
                self._model_id, trust_remote_code=True
            )
            self._model = AutoModelForCausalLM.from_pretrained(
                self._model_id,
                torch_dtype=torch.float16 if device == "cuda" else torch.float32,
                trust_remote_code=True,
            ).to(device)
            self._device = device
            self._loaded = True
            return True
        except ImportError as exc:
            self._load_error = f"transformers/torch not installed: {exc}"
            return False
        except Exception as exc:
            self._load_error = str(exc)
            return False

    def _run_task(self, image, task_prompt: str) -> str:
        """Run a single Florence-2 task prompt and return raw text result."""
        import torch  # type: ignore[import-untyped]

        inputs = self._processor(text=task_prompt, images=image, return_tensors="pt").to(
            self._device
        )
        with torch.no_grad():
            generated_ids = self._model.generate(
                input_ids=inputs["input_ids"],
                pixel_values=inputs["pixel_values"],
                max_new_tokens=1024,
                num_beams=3,
                do_sample=False,
            )
        generated_text = self._processor.batch_decode(
            generated_ids, skip_special_tokens=False
        )[0]
        parsed = self._processor.post_process_generation(
            generated_text,
            task=task_prompt,
            image_size=(image.width, image.height),
        )
        # parsed is typically {task_prompt: <result>}
        raw = parsed.get(task_prompt, "")
        if isinstance(raw, dict):
            return str(raw)
        return str(raw)

    async def describe(
        self,
        image_bytes: bytes,
        mode: str = "caption",
    ) -> ImageDescription:
        t0 = time.monotonic()

        if not self._load():
            return ImageDescription(
                caption=f"[florence2 unavailable: {self._load_error}]",
                tags=[],
                objects=[],
                ocr_text=None,
                backend=self.name,
                ms=0,
            )

        try:
            from PIL import Image as PILImage  # type: ignore[import-untyped]
            import io

            pil_image = PILImage.open(io.BytesIO(image_bytes)).convert("RGB")

            task_key = _TASK_MAP.get(mode, "<CAPTION>")

            caption = ""
            tags: list[str] = []
            objects: list[str] = []
            ocr_text: str | None = None

            if mode == "ocr":
                raw = self._run_task(pil_image, "<OCR>")
                ocr_text = raw
                caption = raw[:200] if raw else ""
            elif mode == "object_detection":
                raw = self._run_task(pil_image, "<OD>")
                # raw is a string repr of dict like {'<OD>': {'bboxes': [...], 'labels': [...]}}
                # Try to extract labels
                cap_text = self._run_task(pil_image, "<CAPTION>")
                caption = cap_text
                try:
                    import ast
                    parsed = ast.literal_eval(raw)
                    if isinstance(parsed, dict):
                        inner = next(iter(parsed.values()), {})
                        objects = inner.get("labels", []) if isinstance(inner, dict) else []
                except Exception:
                    objects = []
            else:
                raw = self._run_task(pil_image, task_key)
                caption = raw

            elapsed_ms = int((time.monotonic() - t0) * 1000)
            return ImageDescription(
                caption=caption,
                tags=tags,
                objects=objects,
                ocr_text=ocr_text,
                backend=self.name,
                ms=elapsed_ms,
            )
        except Exception as exc:
            return ImageDescription(
                caption=f"[florence2 error: {exc}]",
                tags=[],
                objects=[],
                ocr_text=None,
                backend=self.name,
                ms=int((time.monotonic() - t0) * 1000),
            )

    def health(self) -> dict:
        available = self._load_error is None
        return {
            "backend": self.name,
            "model": self._model_id,
            "loaded": self._loaded,
            "available": available,
            "error": self._load_error,
        }
