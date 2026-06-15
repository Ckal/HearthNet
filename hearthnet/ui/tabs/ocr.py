"""OCR tab — extract text from images and PDFs via capability bus."""

from __future__ import annotations

import asyncio
import base64
import concurrent.futures
from typing import Any


def _run(coro):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    return asyncio.run(coro)


def build_ocr_tab(bus: Any | None = None) -> None:
    import gradio as gr

    gr.HTML("""
<div style="background:linear-gradient(135deg,#1e1b4b,#312e81);
            border-radius:10px;padding:16px 20px;margin-bottom:8px;
            border:1px solid #4f46e5">
  <h3 style="color:#fff;margin:0">📄 OCR — Text Extraction</h3>
  <p style="color:rgba(255,255,255,.7);margin:4px 0 0;font-size:.85em">
    Tesseract · TrOCR · extract text from scans, photos, PDFs · offline
  </p>
</div>
""")

    with gr.Row():
        with gr.Column(scale=2):
            ocr_input = gr.File(
                label="Upload image or PDF",
                file_types=[".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".pdf"],
            )
            lang_hint = gr.Textbox(
                label="Language hint (optional)",
                placeholder="eng  deu  fra  auto …",
                value="",
            )
            ocr_btn = gr.Button("📄 Extract Text", variant="primary", size="lg")
        with gr.Column(scale=3):
            ocr_out = gr.Textbox(label="Extracted text", lines=12, interactive=False)
            status_out = gr.Textbox(label="Status", lines=1, interactive=False)

    def _ocr(file_obj, lang: str) -> tuple[str, str]:
        if file_obj is None:
            return "", "⚠ Upload a file first"
        if bus is None:
            return "", "⚠ No bus — run inside a HearthNet node"

        file_path = file_obj if isinstance(file_obj, str) else file_obj.name
        cap = "ocr.pdf" if file_path.lower().endswith(".pdf") else "ocr.image"

        try:
            with open(file_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
        except Exception as exc:
            return "", f"⚠ Could not read file: {exc}"

        async def _call():
            return await bus.call(
                cap, (1, 0),
                {"params": {"language": lang.strip() or None},
                 "input": {"file_b64": b64}},
            )

        try:
            result = _run(_call())
        except Exception as exc:
            return "", f"⚠ Bus error: {exc}"

        if "error" in result:
            if result["error"] == "backend_unavailable":
                return "", "⚠ No OCR backend — install: pip install pytesseract pillow"
            return "", f"⚠ {result.get('message', result['error'])}"

        text = result.get("output", result).get("text", str(result))
        word_count = len(text.split())
        return text, f"✓ Extracted {word_count} words"

    ocr_btn.click(_ocr, inputs=[ocr_input, lang_hint], outputs=[ocr_out, status_out])

    gr.HTML("""
<details style="margin-top:12px">
<summary style="cursor:pointer;color:#94a3b8;font-size:.85em">ℹ Setup help</summary>
<div style="padding:8px 12px;font-size:.85em;color:#94a3b8">
<b>Tesseract:</b> <code>pip install pytesseract pillow</code> + install the Tesseract binary<br>
&nbsp;&nbsp;Ubuntu: <code>apt-get install tesseract-ocr</code><br>
&nbsp;&nbsp;macOS: <code>brew install tesseract</code><br>
&nbsp;&nbsp;Windows: download from <a href="https://github.com/UB-Mannheim/tesseract/wiki">UB-Mannheim</a><br>
<b>Languages:</b> eng (English), deu (German), fra (French), chi_sim (Simplified Chinese), …<br>
Install language packs: <code>apt-get install tesseract-ocr-deu tesseract-ocr-fra</code>
</div>
</details>
""")
