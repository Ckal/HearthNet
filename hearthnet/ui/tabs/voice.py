"""Voice tab — STT transcription and TTS synthesis via the capability bus."""

from __future__ import annotations

import asyncio
import base64
import concurrent.futures
import tempfile
from typing import Any


def _run(coro):
    """Run a coroutine safely regardless of whether an event loop is running."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    return asyncio.run(coro)


def build_voice_tab(bus: Any | None = None) -> None:
    import gradio as gr

    gr.HTML("""
<div style="background:linear-gradient(135deg,#1e1b4b,#312e81);
            border-radius:10px;padding:16px 20px;margin-bottom:8px;
            border:1px solid #4f46e5">
  <h3 style="color:#fff;margin:0">🎙 Voice — STT &amp; TTS</h3>
  <p style="color:rgba(255,255,255,.7);margin:4px 0 0;font-size:.85em">
    Whisper (speech→text) · Edge-TTS 300+ voices (text→speech) · 100% local
  </p>
</div>
""")

    # ── STT ───────────────────────────────────────────────────────────────────
    gr.Markdown("### 🎤 Speech → Text")
    with gr.Row():
        with gr.Column(scale=2):
            stt_audio = gr.Audio(
                label="Upload or record audio",
                type="filepath",
                sources=["upload", "microphone"],
            )
            stt_language = gr.Textbox(
                label="Language hint (optional)",
                placeholder="en  de  fr  auto …",
                value="",
            )
        with gr.Column(scale=3):
            stt_btn = gr.Button("🎤 Transcribe", variant="primary", size="lg")
            stt_out = gr.Textbox(label="Transcript", lines=6, interactive=False)
            stt_status = gr.Textbox(label="Status", lines=1, interactive=False)

    def _transcribe(audio_path: str, language: str) -> tuple[str, str]:
        if not audio_path:
            return "", "⚠ Upload or record audio first"
        if bus is None:
            return "", "⚠ No bus — run inside a HearthNet node"
        try:
            with open(audio_path, "rb") as f:
                audio_b64 = base64.b64encode(f.read()).decode()
        except Exception as exc:
            return "", f"⚠ Could not read file: {exc}"

        async def _call():
            return await bus.call(
                "stt.transcribe", (1, 0),
                {"params": {"language": language.strip() or None},
                 "input": {"audio_b64": audio_b64}},
            )

        try:
            result = _run(_call())
        except Exception as exc:
            return "", f"⚠ Bus error: {exc}"

        if "error" in result:
            if result["error"] == "backend_unavailable":
                return "", "⚠ No STT backend — install: pip install faster-whisper"
            return "", f"⚠ {result.get('message', result['error'])}"
        text = result.get("output", {}).get("text", result.get("text", ""))
        lang = result.get("output", {}).get("language", "")
        return text, f"✓ Transcribed{f' [{lang}]' if lang else ''}"

    stt_btn.click(_transcribe, inputs=[stt_audio, stt_language], outputs=[stt_out, stt_status])

    gr.HTML("<hr style='border-color:#4f46e555;margin:8px 0'>")

    # ── TTS ───────────────────────────────────────────────────────────────────
    gr.Markdown("### 🔊 Text → Speech")
    with gr.Row():
        with gr.Column(scale=2):
            tts_text = gr.Textbox(
                label="Text to speak",
                placeholder="Type anything…",
                lines=5,
            )
            tts_voice = gr.Textbox(
                label="Voice (optional)",
                placeholder="en-US-JennyNeural   de-DE-KatjaNeural   fr-FR-DeniseNeural …",
                value="",
            )
        with gr.Column(scale=3):
            tts_btn = gr.Button("🔊 Synthesize", variant="primary", size="lg")
            tts_audio_out = gr.Audio(label="Generated speech", type="filepath")
            tts_status = gr.Textbox(label="Status", lines=1, interactive=False)

    def _synthesize(text: str, voice: str) -> tuple[str | None, str]:
        if not text.strip():
            return None, "⚠ Enter text to synthesize"
        if bus is None:
            return None, "⚠ No bus — run inside a HearthNet node"

        async def _call():
            return await bus.call(
                "tts.synthesize", (1, 0),
                {"params": {"voice": voice.strip() or None},
                 "input": {"text": text}},
            )

        try:
            result = _run(_call())
        except Exception as exc:
            return None, f"⚠ Bus error: {exc}"

        if "error" in result:
            if result["error"] == "backend_unavailable":
                return None, "⚠ No TTS backend — install: pip install edge-tts"
            return None, f"⚠ {result.get('message', result['error'])}"

        audio_b64 = result.get("output", {}).get("audio_b64", result.get("audio_b64", ""))
        if not audio_b64:
            return None, "⚠ No audio in response"

        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        tmp.write(base64.b64decode(audio_b64))
        tmp.close()
        return tmp.name, "✓ Synthesized"

    tts_btn.click(_synthesize, inputs=[tts_text, tts_voice], outputs=[tts_audio_out, tts_status])

    gr.HTML("""
<details style="margin-top:12px">
<summary style="cursor:pointer;color:#94a3b8;font-size:.85em">ℹ Voice setup help</summary>
<div style="padding:8px 12px;font-size:.85em;color:#94a3b8">
<b>STT:</b> <code>pip install faster-whisper</code> (CPU/GPU) or <code>pip install openai-whisper</code><br>
<b>TTS:</b> <code>pip install edge-tts</code> (free, 300+ voices, needs internet for synthesis)<br>
<b>Example voices:</b> en-US-JennyNeural, en-GB-SoniaNeural, de-DE-KatjaNeural,
fr-FR-DeniseNeural, es-ES-ElviraNeural, ja-JP-NanamiNeural
</div>
</details>
""")
