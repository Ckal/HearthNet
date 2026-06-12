"""NLLB translation backend (facebook/nllb-200-distilled-600M) via transformers."""

from __future__ import annotations

import asyncio
import hashlib
import time
from collections import OrderedDict
from typing import Any

from hearthnet.constants import TRANSLATION_MAX_CHARS
from hearthnet.services.translation.backends.base import TranslationResult

# Top 20 common language pairs (ISO 639-1 → NLLB flores code mapping)
_ISO_TO_FLORES: dict[str, str] = {
    "de": "deu_Latn",
    "en": "eng_Latn",
    "fr": "fra_Latn",
    "es": "spa_Latn",
    "it": "ita_Latn",
    "nl": "nld_Latn",
    "pl": "pol_Latn",
    "pt": "por_Latn",
    "ru": "rus_Cyrl",
    "uk": "ukr_Cyrl",
    "ar": "arb_Arab",
    "tr": "tur_Latn",
    "cs": "ces_Latn",
    "sv": "swe_Latn",
    "da": "dan_Latn",
    "fi": "fin_Latn",
    "ro": "ron_Latn",
    "hu": "hun_Latn",
    "sk": "slk_Latn",
    "hr": "hrv_Latn",
    # Low German / Plattdeutsch — not in standard NLLB; map to nds_Latn if present
    "nds": "nds_Latn",
}

_TOP_PAIRS: list[tuple[str, str]] = [
    ("de", "en"),
    ("en", "de"),
    ("fr", "en"),
    ("en", "fr"),
    ("es", "en"),
    ("en", "es"),
    ("it", "en"),
    ("en", "it"),
    ("nl", "en"),
    ("en", "nl"),
    ("pl", "en"),
    ("en", "pl"),
    ("ru", "en"),
    ("en", "ru"),
    ("uk", "en"),
    ("en", "uk"),
    ("ar", "en"),
    ("en", "ar"),
    ("tr", "en"),
    ("en", "tr"),
]

_LRU_MAX = 1000


class _LRUCache:
    def __init__(self, maxsize: int = _LRU_MAX) -> None:
        self._cache: OrderedDict[str, TranslationResult] = OrderedDict()
        self._maxsize = maxsize

    def get(self, key: str) -> TranslationResult | None:
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    def put(self, key: str, value: TranslationResult) -> None:
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = value
        if len(self._cache) > self._maxsize:
            self._cache.popitem(last=False)


class NllbBackend:
    name = "nllb"

    def __init__(
        self,
        model: str = "facebook/nllb-200-distilled-600M",
        device: str = "auto",
        max_chars: int = TRANSLATION_MAX_CHARS,
    ) -> None:
        self._model_name = model
        self._device = device
        self._max_chars = max_chars
        self._pipeline: Any = None
        self._loaded = False
        self._cache = _LRUCache()
        # Batching
        self._batch_queue: list[tuple[asyncio.Future[str], str, str, str]] = []
        self._batch_task: asyncio.Task[None] | None = None

    @property
    def supported_pairs(self) -> list[tuple[str, str]]:
        return _TOP_PAIRS

    def _resolve_device(self) -> str:
        if self._device != "auto":
            return self._device
        try:
            import torch

            return "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            return "cpu"

    def _load_sync(self) -> None:
        from transformers import pipeline  # type: ignore[import]

        device = self._resolve_device()
        device_id = 0 if device == "cuda" else -1
        self._pipeline = pipeline(
            "translation",
            model=self._model_name,
            device=device_id,
        )
        self._loaded = True

    async def _ensure_loaded(self) -> None:
        if not self._loaded:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._load_sync)

    def health(self) -> dict:
        try:
            import transformers  # noqa: F401
        except ImportError:
            return {
                "backend": self.name,
                "status": "unavailable",
                "reason": "transformers not installed",
            }
        return {"backend": self.name, "status": "ok", "model": self._model_name}

    async def detect_language(self, text: str) -> str:
        """Best-effort language detection using langdetect (optional)."""
        try:
            from langdetect import detect  # type: ignore[import]

            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(None, detect, text)
            return str(result)
        except Exception:
            return "unknown"

    def _cache_key(self, text: str, from_lang: str, to_lang: str) -> str:
        return hashlib.sha256(f"{text}|{from_lang}|{to_lang}".encode()).hexdigest()

    def _translate_sync(self, text: str, from_lang: str, to_lang: str) -> str:
        src_flores = _ISO_TO_FLORES.get(from_lang)
        tgt_flores = _ISO_TO_FLORES.get(to_lang)
        if src_flores is None or tgt_flores is None:
            raise ValueError(f"Unsupported language pair: {from_lang} → {to_lang}")
        output = self._pipeline(
            text,
            src_lang=src_flores,
            tgt_lang=tgt_flores,
            max_length=512,
        )
        return str(output[0]["translation_text"])

    async def translate(
        self,
        text: str,
        from_lang: str,
        to_lang: str,
        domain: str | None = None,
    ) -> TranslationResult:
        if len(text) > self._max_chars:
            raise ValueError(f"Text too long: {len(text)} > {self._max_chars}")

        # Handle auto-detect
        if from_lang == "auto":
            from_lang = await self.detect_language(text)

        cache_key = self._cache_key(text, from_lang, to_lang)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        await self._ensure_loaded()

        # Enqueue and batch within 100ms window
        translated_text = await self._enqueue_or_translate(text, from_lang, to_lang)

        t0 = time.monotonic()
        result = TranslationResult(
            text=translated_text,
            from_lang=from_lang,
            to_lang=to_lang,
            backend=self.name,
            ms=int((time.monotonic() - t0) * 1000) + 1,
        )
        self._cache.put(cache_key, result)
        return result

    async def _enqueue_or_translate(self, text: str, from_lang: str, to_lang: str) -> str:
        """Add to batch queue and wait up to 100ms for batch processing."""
        loop = asyncio.get_running_loop()
        future: asyncio.Future[str] = loop.create_future()
        self._batch_queue.append((future, text, from_lang, to_lang))

        if self._batch_task is None or self._batch_task.done():
            self._batch_task = asyncio.create_task(self._flush_batch_after_delay())

        return await future

    async def _flush_batch_after_delay(self) -> None:
        await asyncio.sleep(0.1)  # 100ms window
        if not self._batch_queue:
            return
        batch = self._batch_queue[:8]
        self._batch_queue = self._batch_queue[8:]
        loop = asyncio.get_running_loop()

        # Group by (from_lang, to_lang) for efficient batching
        groups: dict[tuple[str, str], list[tuple[asyncio.Future[str], str]]] = {}
        for future, text, fl, tl in batch:
            key = (fl, tl)
            groups.setdefault(key, []).append((future, text))

        for (fl, tl), items in groups.items():
            texts = [t for _, t in items]
            futures_grp = [f for f, _ in items]
            try:
                results = await loop.run_in_executor(
                    None, self._translate_batch_sync, texts, fl, tl
                )
                for f, r in zip(futures_grp, results, strict=False):
                    if not f.done():
                        f.set_result(r)
            except Exception as exc:
                for f in futures_grp:
                    if not f.done():
                        f.set_exception(exc)

    def _translate_batch_sync(self, texts: list[str], from_lang: str, to_lang: str) -> list[str]:
        src_flores = _ISO_TO_FLORES.get(from_lang)
        tgt_flores = _ISO_TO_FLORES.get(to_lang)
        if src_flores is None or tgt_flores is None:
            raise ValueError(f"Unsupported language pair: {from_lang} → {to_lang}")
        outputs = self._pipeline(
            texts,
            src_lang=src_flores,
            tgt_lang=tgt_flores,
            max_length=512,
        )
        return [str(o["translation_text"]) for o in outputs]
