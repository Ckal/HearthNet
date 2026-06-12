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


import os as _os

_WEBAGENT_INDEX = _os.path.abspath(
    _os.path.join(_os.path.dirname(__file__), "..", "..", "webagent", "index.html")
)

# Ticker HTML — static items, doubled for seamless loop
_EGG_HTML = """
<div class="hn-ticker">
  <span class="hn-lbl">⚡ LIVE</span>
  <div class="hn-track">
    <span class="hn-item"><b>BleepingComputer</b> — Security Alerts</span>
    <span class="hn-item"><b>Reuters</b> — World News</span>
    <span class="hn-item"><b>TechCrunch</b> — Tech Headlines</span>
    <span class="hn-item"><b>BBC</b> — Breaking News</span>
    <span class="hn-item"><b>AP News</b> — Top Stories</span>
    <span class="hn-item"><b>DW</b> — Global Updates</span>
    <span class="hn-item"><b>Al Jazeera</b> — International</span>
    <span class="hn-item"><b>BleepingComputer</b> — Security Alerts</span>
    <span class="hn-item"><b>Reuters</b> — World News</span>
    <span class="hn-item"><b>TechCrunch</b> — Tech Headlines</span>
    <span class="hn-item"><b>BBC</b> — Breaking News</span>
    <span class="hn-item"><b>AP News</b> — Top Stories</span>
    <span class="hn-item"><b>DW</b> — Global Updates</span>
    <span class="hn-item"><b>Al Jazeera</b> — International</span>
  </div>
</div>
<div class="hn-modal">
  <div class="hn-modal-box">
    <button class="hn-close" title="Close (Esc)">×</button>
    <iframe class="hn-iframe" src="file={webagent}" allow="microphone; camera"></iframe>
  </div>
</div>
""".format(webagent=_WEBAGENT_INDEX.replace("\\", "/"))

# js_on_load — runs in component context, 'element' is the component root.
# Injects global CSS via document.head (no stacking-context issues), then
# moves ticker + modal to document.body so position:fixed works correctly.
_EGG_JS = """
    // ── Inject global CSS once ──────────────────────────────────────────────
    if (!document.getElementById('hn-egg-styles')) {
        const s = document.createElement('style');
        s.id = 'hn-egg-styles';
        s.textContent = `
            .hn-ticker {
                display: none;
                position: fixed !important;
                top: 0; left: 0; right: 0;
                height: 48px;
                background: linear-gradient(90deg, #111 0%, #1e1e1e 100%);
                border-bottom: 2px solid #ff6b35;
                color: #fff;
                font-family: monospace;
                font-size: 13px;
                overflow: hidden;
                z-index: 99998;
                align-items: center;
                padding: 0 16px;
                box-shadow: 0 3px 12px rgba(0,0,0,.6);
            }
            .hn-ticker.hn-on { display: flex !important; }
            .hn-lbl { white-space: nowrap; margin-right: 16px; font-weight: bold; color: #ff6b35; flex-shrink: 0; }
            .hn-track { display: flex; animation: hn-scroll 30s linear infinite; white-space: nowrap; }
            .hn-track:hover { animation-play-state: paused; }
            .hn-item { padding: 0 40px 0 0; color: #ccc; }
            .hn-item b { color: #ff9955; }
            @keyframes hn-scroll { 0% { transform: translateX(0); } 100% { transform: translateX(-50%); } }
            .hn-modal {
                display: none;
                position: fixed !important;
                inset: 0;
                background: rgba(0,0,0,.82);
                z-index: 99999;
            }
            .hn-modal.hn-on { display: flex !important; align-items: center; justify-content: center; }
            .hn-modal-box {
                background: #fff;
                border-radius: 10px;
                width: 92vw; height: 88vh;
                position: relative;
                overflow: hidden;
                box-shadow: 0 20px 60px rgba(0,0,0,.5);
            }
            .hn-close {
                position: absolute; top: 8px; right: 12px;
                font-size: 24px; line-height: 1; cursor: pointer;
                background: rgba(255,255,255,.9); border: 1px solid #ccc;
                border-radius: 50%; width: 32px; height: 32px; z-index: 100000;
                display: flex; align-items: center; justify-content: center;
            }
            .hn-close:hover { background: #f0f0f0; }
            .hn-iframe { width: 100%; height: 100%; border: none; }
        `;
        document.head.appendChild(s);
    }

    // ── Move elements to body (escapes all Gradio stacking contexts) ────────
    const ticker = element.querySelector('.hn-ticker');
    const modal  = element.querySelector('.hn-modal');
    if (!ticker || !modal) return;
    document.body.appendChild(ticker);
    document.body.appendChild(modal);

    // ── Wire up close button and overlay click ──────────────────────────────
    const closeBtn = modal.querySelector('.hn-close');
    closeBtn.addEventListener('click', () => modal.classList.remove('hn-on'));
    modal.addEventListener('click', e => { if (e.target === modal) modal.classList.remove('hn-on'); });

    // ── Keyboard shortcuts ──────────────────────────────────────────────────
    document.addEventListener('keydown', evt => {
        const tag = (document.activeElement || {}).tagName || '';
        if (['INPUT', 'TEXTAREA', 'SELECT'].includes(tag)) return;
        if (evt.key === 'e' || evt.key === 'E') {
            ticker.classList.toggle('hn-on');
        } else if (evt.key === 'a' || evt.key === 'A') {
            modal.classList.toggle('hn-on');
        } else if (evt.key === 'Escape') {
            ticker.classList.remove('hn-on');
            modal.classList.remove('hn-on');
        }
    });
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
            # Easter egg ticker + agent modal via Gradio 6 js_on_load API
            gr.HTML(html_template=_EGG_HTML, js_on_load=_EGG_JS)

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
