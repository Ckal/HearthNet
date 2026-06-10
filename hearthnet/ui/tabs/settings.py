"""Settings tab."""
from __future__ import annotations


def build_settings_tab(config=None, meta: dict | None = None):
    import gradio as gr

    meta = meta or {}

    with gr.Column():
        gr.Markdown("### Settings")

        gr.Markdown("#### Node Identity")
        gr.Markdown(f"Node ID: `{meta.get('node_id', 'not initialized')[:30]}`")
        gr.Markdown(f"Profile: `{meta.get('profile', 'hearth')}`")

        gr.Markdown("#### Community")
        gr.Markdown(f"Community: `{meta.get('community_id', 'none')[:30]}`")

        if config is not None:
            gr.Markdown("#### Configuration")
            gr.Markdown(
                f"Transport port: `{getattr(getattr(config, 'transport', None), 'port', 7080)}`"
            )
            gr.Markdown(
                f"Discovery mDNS: `{getattr(getattr(config, 'discovery', None), 'mdns_enabled', True)}`"
            )

        gr.Markdown("#### Phase Labels")
        gr.Markdown(
            """
| Module | Status |
|--------|--------|
| M01 Identity | ✅ Implemented |
| M02 Discovery | ✅ Implemented (mDNS/UDP) |
| M03 Bus | ✅ Implemented |
| M04 LLM | ✅ Implemented (Ollama/llama.cpp/HF) |
| M05 RAG | ✅ Implemented |
| M06 Marketplace | ✅ Implemented (event-sourced) |
| M07 Blobs | ✅ Implemented |
| M08 UI | ✅ This UI |
| M09 Emergency | ✅ Implemented |
| M10 Chat | ✅ Implemented |
| M11 Embedding | ✅ Implemented |
| M12 CLI | ✅ Implemented |
| M13 Onboarding | ✅ Implemented |
| X01 Transport | ✅ Implemented (FastAPI) |
| X02 Events | ✅ Implemented (SQLite) |
| X03 Observability | ✅ Implemented |
| X04 Config | ✅ Implemented |
"""
        )
