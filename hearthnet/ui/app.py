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


# Easter egg ticker CSS (no script - will be injected via Blocks head parameter)
_EASTER_EGG_CSS = """
<style id="egg-ticker-style">
    body {
        position: relative;
    }
    .egg-ticker {
        position: fixed;
        top: -100px;
        left: 0;
        right: 0;
        height: 60px;
        background: linear-gradient(90deg, #1a1a1a, #2a2a2a);
        border-bottom: 2px solid #ff6b35;
        color: #fff;
        font-size: 14px;
        overflow: hidden;
        z-index: 9999;
        display: flex;
        align-items: center;
        padding: 0 20px;
        transition: top 0.3s ease;
        box-shadow: 0 2px 10px rgba(0,0,0,0.5);
    }
    .egg-ticker.active {
        top: 0;
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
    
    /* Modal for agent page */
    .egg-modal-overlay {
        display: none;
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: rgba(0, 0, 0, 0.8);
        z-index: 10000;
        animation: fadeIn 0.3s ease;
    }
    .egg-modal-overlay.active {
        display: flex;
        align-items: center;
        justify-content: center;
    }
    .egg-modal-content {
        background: #fff;
        border-radius: 8px;
        width: 90%;
        height: 90%;
        max-width: 1200px;
        max-height: 900px;
        overflow: auto;
        position: relative;
        box-shadow: 0 10px 40px rgba(0, 0, 0, 0.3);
    }
    .egg-modal-close {
        position: absolute;
        top: 10px;
        right: 15px;
        font-size: 28px;
        font-weight: bold;
        color: #999;
        cursor: pointer;
        z-index: 10001;
        background: #fff;
        width: 35px;
        height: 35px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        border: 1px solid #ddd;
    }
    .egg-modal-close:hover {
        color: #000;
        background: #f0f0f0;
    }
    .egg-modal-iframe {
        width: 100%;
        height: 100%;
        border: none;
        border-radius: 8px;
    }
    
    @keyframes scroll {
        0% { transform: translateX(0); }
        100% { transform: translateX(-100%); }
    }
    @keyframes fadeIn {
        from { opacity: 0; }
        to { opacity: 1; }
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
<div id="egg-modal-overlay" class="egg-modal-overlay">
    <div class="egg-modal-content">
        <span id="egg-modal-close" class="egg-modal-close">×</span>
        <iframe id="egg-modal-iframe" class="egg-modal-iframe" src="http://127.0.0.1:8099/index.html"></iframe>
    </div>
</div>
"""

# Easter egg script - injected via Blocks head parameter
_EASTER_EGG_SCRIPT = """
<script>
(function() {
    let eggOpen = false;
    let modalOpen = false;
    
    function initEasterEgg() {
        const ticker = document.getElementById('egg-ticker');
        const modalOverlay = document.getElementById('egg-modal-overlay');
        const modalClose = document.getElementById('egg-modal-close');
        
        if (!ticker || !modalOverlay) {
            setTimeout(initEasterEgg, 100);
            return;
        }

        window.toggleEasterEgg = function() {
            eggOpen = !eggOpen;
            ticker.classList.toggle('active', eggOpen);
        };
        
        window.toggleAgentModal = function() {
            modalOpen = !modalOpen;
            modalOverlay.classList.toggle('active', modalOpen);
        };
        
        // Close modal when close button clicked
        modalClose.addEventListener('click', function() {
            window.toggleAgentModal();
        });
        
        // Close modal when overlay (not content) clicked
        modalOverlay.addEventListener('click', function(e) {
            if (e.target === modalOverlay) {
                window.toggleAgentModal();
            }
        });

        document.addEventListener('keydown', function(evt) {
            if (document.activeElement && 
                ['INPUT', 'TEXTAREA'].includes(document.activeElement.tagName)) {
                return;
            }
            
            if (evt.key === 'e' || evt.key === 'E') {
                window.toggleEasterEgg();
            } else if (evt.key === 'a' || evt.key === 'A') {
                window.toggleAgentModal();
            }
        });
    }
    
    initEasterEgg();
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

        with gr.Blocks(title=f"HearthNet — {display_name}", head=_EASTER_EGG_SCRIPT) as demo:
            # Inject easter egg ticker CSS & HTML
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
