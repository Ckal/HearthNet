"""Image tab — Florence2 visual description via capability bus."""

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


def build_image_tab(bus: Any | None = None) -> None:
    import gradio as gr

    gr.HTML("""
<div style="background:linear-gradient(135deg,#1e1b4b,#312e81);
            border-radius:10px;padding:16px 20px;margin-bottom:8px;
            border:1px solid #4f46e5">
  <h3 style="color:#fff;margin:0">🖼 Image — Visual AI</h3>
  <p style="color:rgba(255,255,255,.7);margin:4px 0 0;font-size:.85em">
    Florence2 vision model · describe scenes · read text · detect objects · 100% local
  </p>
</div>
""")

    with gr.Row():
        with gr.Column(scale=2):
            img_input = gr.Image(type="filepath", label="Upload image")
            task_select = gr.Radio(
                choices=["Describe", "Detailed Caption", "OCR (read text in image)"],
                value="Describe",
                label="Task",
            )
            describe_btn = gr.Button("🔍 Analyse Image", variant="primary", size="lg")
        with gr.Column(scale=3):
            description_out = gr.Textbox(label="Result", lines=8, interactive=False)
            status_out = gr.Textbox(label="Status", lines=1, interactive=False)

    def _describe(path: str | None, task: str) -> tuple[str, str]:
        if not path:
            return "", "⚠ Upload an image first"
        if bus is None:
            return "", "⚠ No bus — run inside a HearthNet node"
        try:
            with open(path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
        except Exception as exc:
            return "", f"⚠ Could not read file: {exc}"

        task_map = {
            "Describe": "caption",
            "Detailed Caption": "detailed_caption",
            "OCR (read text in image)": "ocr",
        }
        task_key = task_map.get(task, "caption")

        async def _call():
            return await bus.call(
                "img.describe", (1, 0),
                {"params": {"task": task_key},
                 "input": {"image_b64": b64}},
            )

        try:
            result = _run(_call())
        except Exception as exc:
            return "", f"⚠ Bus error: {exc}"

        if "error" in result:
            if result["error"] == "backend_unavailable":
                return "", "⚠ No vision backend — Florence2 model not loaded"
            return "", f"⚠ {result.get('message', result['error'])}"

        out = result.get("output", result)
        caption = out.get("caption", out.get("text", str(out)))
        return caption, "✓ Done"

    describe_btn.click(_describe, inputs=[img_input, task_select], outputs=[description_out, status_out])

    gr.HTML("""
<details style="margin-top:12px">
<summary style="cursor:pointer;color:#94a3b8;font-size:.85em">ℹ Setup help</summary>
<div style="padding:8px 12px;font-size:.85em;color:#94a3b8">
Florence2 loads automatically if <code>transformers</code> and <code>timm</code> are installed.<br>
For GPU acceleration: <code>pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121</code><br>
Model: <code>microsoft/Florence-2-base</code> (~900MB download on first use)
</div>
</details>
""")
