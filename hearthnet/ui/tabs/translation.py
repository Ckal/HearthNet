"""Translation tab — NLLB-200 multilingual translation via capability bus."""

from __future__ import annotations

import asyncio
import concurrent.futures
from typing import Any

_LANGUAGES = [
    "auto", "en", "de", "fr", "es", "pt", "it", "nl", "pl", "ru",
    "zh", "ja", "ko", "ar", "hi", "tr", "sv", "da", "fi", "no",
    "cs", "ro", "hu", "uk", "vi", "th", "id", "ms", "fa", "he",
]

_LANG_NAMES = {
    "auto": "Auto-detect", "en": "English", "de": "German", "fr": "French",
    "es": "Spanish", "pt": "Portuguese", "it": "Italian", "nl": "Dutch",
    "pl": "Polish", "ru": "Russian", "zh": "Chinese", "ja": "Japanese",
    "ko": "Korean", "ar": "Arabic", "hi": "Hindi", "tr": "Turkish",
    "sv": "Swedish", "da": "Danish", "fi": "Finnish", "no": "Norwegian",
    "cs": "Czech", "ro": "Romanian", "hu": "Hungarian", "uk": "Ukrainian",
    "vi": "Vietnamese", "th": "Thai", "id": "Indonesian", "ms": "Malay",
    "fa": "Persian", "he": "Hebrew",
}


def _run(coro):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    return asyncio.run(coro)


def build_translation_tab(bus: Any | None = None) -> None:
    import gradio as gr

    gr.HTML("""
<div style="background:linear-gradient(135deg,#1e1b4b,#312e81);
            border-radius:10px;padding:16px 20px;margin-bottom:8px;
            border:1px solid #4f46e5">
  <h3 style="color:#fff;margin:0">🌍 Translation — 200 Languages</h3>
  <p style="color:rgba(255,255,255,.7);margin:4px 0 0;font-size:.85em">
    NLLB-200 · Meta's No Language Left Behind · 200 languages · offline-first
  </p>
</div>
""")

    lang_choices = [f"{code} — {_LANG_NAMES[code]}" for code in _LANGUAGES]

    with gr.Row():
        with gr.Column(scale=2):
            src_text = gr.Textbox(
                label="Text to translate",
                placeholder="Enter text here…",
                lines=6,
            )
            with gr.Row():
                src_lang = gr.Dropdown(
                    choices=lang_choices,
                    value="auto — Auto-detect",
                    label="From",
                )
                tgt_lang = gr.Dropdown(
                    choices=[c for c in lang_choices if not c.startswith("auto")],
                    value="de — German",
                    label="To",
                )
            translate_btn = gr.Button("🌍 Translate", variant="primary", size="lg")
        with gr.Column(scale=3):
            out_text = gr.Textbox(label="Translation", lines=6, interactive=False)
            status_out = gr.Textbox(label="Status", lines=1, interactive=False)

    def _translate(text: str, src: str, tgt: str) -> tuple[str, str]:
        if not text.strip():
            return "", "⚠ Enter text to translate"
        if bus is None:
            return "", "⚠ No bus — run inside a HearthNet node"

        src_code = src.split(" —")[0].strip()
        tgt_code = tgt.split(" —")[0].strip()
        if src_code == "auto":
            src_code = None

        async def _call():
            return await bus.call(
                "trans.text", (1, 0),
                {"params": {"source_lang": src_code, "target_lang": tgt_code},
                 "input": {"text": text}},
            )

        try:
            result = _run(_call())
        except Exception as exc:
            return "", f"⚠ Bus error: {exc}"

        if "error" in result:
            if result["error"] == "backend_unavailable":
                return "", "⚠ No translation backend — install: pip install transformers sentencepiece"
            return "", f"⚠ {result.get('message', result['error'])}"

        translated = result.get("output", result).get("text", str(result))
        detected = result.get("output", result).get("detected_lang", "")
        note = f" (detected: {detected})" if detected and not src_code else ""
        return translated, f"✓ Translated{note}"

    translate_btn.click(
        _translate,
        inputs=[src_text, src_lang, tgt_lang],
        outputs=[out_text, status_out],
    )

    gr.HTML("""
<details style="margin-top:12px">
<summary style="cursor:pointer;color:#94a3b8;font-size:.85em">ℹ Setup help</summary>
<div style="padding:8px 12px;font-size:.85em;color:#94a3b8">
<b>Requirements:</b> <code>pip install transformers sentencepiece torch</code><br>
<b>Model:</b> <code>facebook/nllb-200-distilled-600M</code> (~2.5GB) — loads on first use<br>
<b>200 languages supported</b> including low-resource languages not covered by Google Translate<br>
<b>Offline:</b> once the model is downloaded, translation works without internet
</div>
</details>
""")
