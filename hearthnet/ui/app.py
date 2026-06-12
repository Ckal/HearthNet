"""M08 — UI: HearthNet Gradio dashboard.

The UI's strict rule: it NEVER imports a service module directly.
All data comes via bus.call() or bus introspection APIs.
"""

from __future__ import annotations

import contextlib
from typing import Any

try:
    import gradio as gr

    HAS_GRADIO = True
except ImportError:
    HAS_GRADIO = False


# Inject easter egg ticker CSS/HTML into Gradio's head
_EASTER_EGG_CSS = """
<style id="egg-ticker-style">
    body {
        position: relative;
    }
    .egg-ticker {
        position: fixed;
        bottom: -100px;
        left: 0;
        right: 0;
        height: 60px;
        background: linear-gradient(90deg, #1a1a1a, #2a2a2a);
        border-top: 2px solid #ff6b35;
        color: #fff;
        font-size: 14px;
        overflow: hidden;
        z-index: 9999;
        display: flex;
        align-items: center;
        padding: 0 20px;
        transition: bottom 0.3s ease;
        box-shadow: 0 -2px 10px rgba(0,0,0,0.5);
    }
    .egg-ticker.active {
        bottom: 0;
    }
    .egg-label {
        white-space: nowrap;
        margin-right: 20px;
        font-weight: bold;
        color: #ff6b35;
        min-width: 70px;
    }
    .egg-track {
        display: flex;
        animation: scroll 20s linear infinite;
        white-space: nowrap;
        gap: 40px;
    }
    .egg-track:hover {
        animation-play-state: paused;
    }
    .etk {
        display: inline-block;
        padding: 0 40px;
        color: #ccc;
    }
    .etk b {
        color: #ff6b35;
        font-weight: bold;
    }
    @keyframes scroll {
        0% { transform: translateX(0); }
        100% { transform: translateX(-100%); }
    }
</style>
<div id="egg-ticker" class="egg-ticker">
    <div class="egg-label">⚡ LIVE</div>
    <div id="egg-track" class="egg-track">
        <span class="etk"><b>BleepingComputer</b> Security Updates</span>
        <span class="etk"><b>Reuters</b> World News</span>
        <span class="etk"><b>TechCrunch</b> Latest</span>
        <span class="etk"><b>BBC</b> Breaking</span>
        <span class="etk"><b>AP News</b> Top Stories</span>
    </div>
</div>
<script id="egg-ticker-script">
    (function() {
        let eggOpen = false;
        const ticker = document.getElementById('egg-ticker');
        if (!ticker) return;

        // Attach to window so it survives navigation
        window.toggleEasterEgg = function() {
            eggOpen = !eggOpen;
            if (ticker) {
                ticker.classList.toggle('active', eggOpen);
            }
        };

        // Listen for 'e' key
        document.addEventListener('keydown', function(evt) {
            if ((evt.key === 'e' || evt.key === 'E') &&
                document.activeElement &&
                !['INPUT', 'TEXTAREA'].includes(document.activeElement.tagName)) {
                window.toggleEasterEgg();
            }
        });
    })();
</script>
"""


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
        from hearthnet.ui.tabs.getting_started import build_getting_started_tab
        from hearthnet.ui.tabs.marketplace import build_marketplace_tab
        from hearthnet.ui.tabs.mesh import build_mesh_tab
        from hearthnet.ui.tabs.settings import build_settings_tab

        # Pull identity from bus when not explicitly provided in meta
        if self._bus is not None:
            self._meta.setdefault("node_id", getattr(self._bus, "node_id_full", "unknown"))
            self._meta.setdefault("community_id", getattr(self._bus, "community_id", "unknown"))

        node_id_display = self._meta.get("node_id", "unknown")
        display_name = self._meta.get("display_name", node_id_display[:20])

        with gr.Blocks(title=f"HearthNet — {display_name}") as demo:
            # Inject easter egg ticker
            gr.HTML(value=_EASTER_EGG_CSS)

            gr.Markdown(f"# 🔥 HearthNet — {display_name}")

            with gr.Row():
                gr.HTML(value="<span style='color:green'>● ONLINE</span>")
                gr.Markdown(f"Node: `{node_id_display[:40]}`")
                gr.Markdown(f"Community: `{self._meta.get('community_id', 'unknown')[:30]}`")

            with gr.Tabs():
                with gr.Tab("Ask"):
                    build_ask_tab(self._bus)
                with gr.Tab("Chat"):
                    build_chat_tab(self._bus)
                with gr.Tab("Mesh"):
                    build_mesh_tab(self._bus)
                with gr.Tab("Marketplace"):
                    build_marketplace_tab(self._bus)
                with gr.Tab("Files"):
                    build_files_tab(self._bus)
                with gr.Tab("Emergency"):
                    build_emergency_tab(self._bus, self._state_bus)
                with gr.Tab("Settings"):
                    build_settings_tab(self._config, self._meta, bus=self._bus)
                with gr.Tab("Getting Started"):
                    build_getting_started_tab()

        self._demo = demo
        return demo

    async def shutdown(self) -> None:
        if self._demo:
            with contextlib.suppress(Exception):
                self._demo.close()


def build_ui(bus, state_bus=None, config=None, **meta) -> UiApp:
    """Convenience constructor used by node.py."""
    return UiApp(bus=bus, state_bus=state_bus, config=config, **meta)
