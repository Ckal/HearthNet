"""M08 — UI: HearthNet Gradio dashboard.

The UI's strict rule: it NEVER imports a service module directly.
All data comes via bus.call() or bus introspection APIs.
"""
from __future__ import annotations

from typing import Any

try:
    import gradio as gr

    HAS_GRADIO = True
except ImportError:
    HAS_GRADIO = False


class UiApp:
    def __init__(self, bus=None, state_bus=None, config=None, **meta):
        self._bus = bus
        self._state_bus = state_bus
        self._config = config
        self._meta = meta
        self._demo = None

    def build(self) -> Any:
        """Build and return the Gradio Blocks app."""
        if not HAS_GRADIO:
            raise ImportError("gradio not installed")
        from hearthnet.ui.tabs.ask import build_ask_tab
        from hearthnet.ui.tabs.chat import build_chat_tab
        from hearthnet.ui.tabs.emergency import build_emergency_tab
        from hearthnet.ui.tabs.files import build_files_tab
        from hearthnet.ui.tabs.marketplace import build_marketplace_tab
        from hearthnet.ui.tabs.settings import build_settings_tab

        with gr.Blocks(title="HearthNet", theme=gr.themes.Soft()) as demo:
            gr.Markdown("# 🔥 HearthNet — Community AI Mesh")

            with gr.Row():
                gr.HTML(value="<span style='color:green'>● ONLINE</span>")
                gr.Markdown(f"Node: `{self._meta.get('node_id', 'unknown')[:20]}`")

            with gr.Tabs():
                with gr.Tab("Ask"):
                    build_ask_tab(self._bus)
                with gr.Tab("Chat"):
                    build_chat_tab(self._bus)
                with gr.Tab("Marketplace"):
                    build_marketplace_tab(self._bus)
                with gr.Tab("Files"):
                    build_files_tab(self._bus)
                with gr.Tab("Emergency"):
                    build_emergency_tab(self._bus, self._state_bus)
                with gr.Tab("Settings"):
                    build_settings_tab(self._config, self._meta)

        self._demo = demo
        return demo

    async def shutdown(self) -> None:
        if self._demo:
            try:
                self._demo.close()
            except Exception:
                pass


def build_ui(bus, state_bus=None, config=None, **meta) -> UiApp:
    """Convenience constructor used by node.py."""
    return UiApp(bus=bus, state_bus=state_bus, config=config, **meta)
