"""Voice tab — STT transcription and TTS synthesis via the capability bus."""

from __future__ import annotations

from typing import Any


def build_voice_tab(bus: Any | None = None) -> None:
    import gradio as gr

    gr.Markdown(
        """
## 🎙 Voice — Speech-to-Text & Text-to-Speech

All processing runs **locally** on this node via the capability bus.
- **STT**: Whisper (openai-whisper / faster-whisper)
- **TTS**: Edge-TTS (free, 300+ voices, no API key needed)
"""
    )

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
                placeholder="en, de, fr, auto …",
                value="",
            )
        with gr.Column(scale=3):
            stt_btn = gr.Button("🎤 Transcribe", variant="primary")
            stt_out = gr.Textbox(label="Transcript", lines=6, interactive=False)
            stt_status = gr.Textbox(label="Status", lines=1, interactive=False)

    def _transcribe(audio_path: str, language: str) -> tuple[str, str]:
        if not audio_path:
            return "", "⚠ Upload or record audio first"
        if bus is None:
            return "", "⚠ No bus — run inside a HearthNet node"
        import asyncio, base64

        try:
            with open(audio_path, "rb") as f:
                audio_b64 = base64.b64encode(f.read()).decode()
        except Exception as exc:
            return "", f"⚠ Could not read file: {exc}"

        body = {
            "params": {"language": language.strip() or None},
            "input": {"audio_b64": audio_b64},
        }
        try:
            result = asyncio.get_event_loop().run_until_complete(
                bus.call("stt.transcribe", (1, 0), body)
            )
        except Exception as exc:
            return "", f"⚠ Bus error: {exc}"

        if "error" in result:
            return "", f"⚠ {result['error']}: {result.get('message', '')}"
        text = result.get("output", {}).get("text", result.get("text", ""))
        lang = result.get("output", {}).get("language", "")
        return text, f"✓ Transcribed{f' [{lang}]' if lang else ''}"

    stt_btn.click(_transcribe, inputs=[stt_audio, stt_language], outputs=[stt_out, stt_status])

    gr.Markdown("---")

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
                placeholder="en-US-JennyNeural, de-DE-KatjaNeural …",
                value="",
            )
        with gr.Column(scale=3):
            tts_btn = gr.Button("🔊 Synthesize", variant="primary")
            tts_audio_out = gr.Audio(label="Generated speech", type="filepath")
            tts_status = gr.Textbox(label="Status", lines=1, interactive=False)

    def _synthesize(text: str, voice: str) -> tuple[str | None, str]:
        if not text.strip():
            return None, "⚠ Enter text to synthesize"
        if bus is None:
            return None, "⚠ No bus — run inside a HearthNet node"
        import asyncio, base64, tempfile, os

        body = {
            "params": {"voice": voice.strip() or None},
            "input": {"text": text},
        }
        try:
            result = asyncio.get_event_loop().run_until_complete(
                bus.call("tts.synthesize", (1, 0), body)
            )
        except Exception as exc:
            return None, f"⚠ Bus error: {exc}"

        if "error" in result:
            return None, f"⚠ {result['error']}: {result.get('message', '')}"

        audio_b64 = result.get("output", {}).get("audio_b64", result.get("audio_b64", ""))
        if not audio_b64:
            return None, "⚠ No audio in response"

        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        tmp.write(base64.b64decode(audio_b64))
        tmp.close()
        return tmp.name, "✓ Synthesized"

    tts_btn.click(_synthesize, inputs=[tts_text, tts_voice], outputs=[tts_audio_out, tts_status])
