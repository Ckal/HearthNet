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


# Easter egg ticker — raw CSS for gr.Blocks(css=...) (no <style> tags, Gradio injects it)
_EASTER_EGG_RAW_CSS = """
    #hn-egg-ticker {
        position: fixed !important;
        top: -80px;
        left: 0;
        right: 0;
        height: 48px;
        background: linear-gradient(90deg, #111, #1e1e1e);
        border-bottom: 2px solid #ff6b35;
        color: #fff;
        font-size: 14px;
        overflow: hidden;
        z-index: 99999;
        display: flex;
        align-items: center;
        padding: 0 16px;
        transition: top 0.35s ease;
        box-shadow: 0 3px 12px rgba(0,0,0,0.6);
        font-family: monospace;
    }
    #hn-egg-ticker.hn-active {
        top: 0 !important;
    }
    #hn-egg-ticker .hn-label {
        white-space: nowrap;
        margin-right: 16px;
        font-weight: bold;
        color: #ff6b35;
        min-width: 65px;
        flex-shrink: 0;
    }
    #hn-egg-ticker .hn-track {
        display: flex;
        animation: hn-marquee 25s linear infinite;
        white-space: nowrap;
    }
    #hn-egg-ticker .hn-track:hover {
        animation-play-state: paused;
    }
    #hn-egg-ticker .hn-item {
        display: inline-block;
        padding: 0 48px 0 0;
        color: #ccc;
    }
    #hn-egg-ticker .hn-item b {
        color: #ff9955;
    }
    #hn-egg-modal {
        display: none;
        position: fixed !important;
        inset: 0;
        background: rgba(0,0,0,0.82);
        z-index: 100000;
    }
    #hn-egg-modal.hn-active {
        display: flex;
        align-items: center;
        justify-content: center;
    }
    #hn-egg-modal-inner {
        background: #fff;
        border-radius: 10px;
        width: 92vw;
        height: 88vh;
        max-width: 1300px;
        position: relative;
        overflow: hidden;
        box-shadow: 0 20px 60px rgba(0,0,0,0.5);
    }
    #hn-egg-modal-close {
        position: absolute;
        top: 8px;
        right: 12px;
        font-size: 26px;
        line-height: 1;
        cursor: pointer;
        color: #444;
        z-index: 100001;
        background: rgba(255,255,255,0.9);
        border-radius: 50%;
        width: 32px;
        height: 32px;
        display: flex;
        align-items: center;
        justify-content: center;
        border: 1px solid #ccc;
    }
    #hn-egg-modal-close:hover { background: #eee; }
    #hn-egg-iframe {
        width: 100%;
        height: 100%;
        border: none;
    }
    @keyframes hn-marquee {
        0%   { transform: translateX(0); }
        100% { transform: translateX(-50%); }
    }
"""

# HTML injected via gr.HTML() – no inline styles, no scripts, pure elements
_EASTER_EGG_HTML = ""

# JavaScript injected via gr.Blocks(js=...) – Gradio 4+ native, runs on page load
# NOTE: gr.Blocks(js=) expects a *function body* string (no wrapping function needed)
_EASTER_EGG_JS = r"""
() => {
    // Build ticker element and append to document.body (escapes Gradio's stacking context)
    function buildTicker() {
        const t = document.createElement('div');
        t.id = 'hn-egg-ticker';
        // Duplicate items for seamless loop
        const items = [
            ['BleepingComputer', 'Cyber Security Alerts'],
            ['Reuters', 'World News'],
            ['TechCrunch', 'Tech Headlines'],
            ['BBC', 'Breaking News'],
            ['AP News', 'Top Stories'],
            ['DW', 'Global Updates'],
            ['Al Jazeera', 'International'],
        ];
        const doubled = [...items, ...items];
        const track = document.createElement('div');
        track.className = 'hn-track';
        doubled.forEach(([src, title]) => {
            const s = document.createElement('span');
            s.className = 'hn-item';
            s.innerHTML = '<b>' + src + '</b> — ' + title;
            track.appendChild(s);
        });
        t.innerHTML = '<span class="hn-label">⚡ LIVE</span>';
        t.appendChild(track);
        document.body.appendChild(t);
        return t;
    }

    // Build modal and append to document.body
    function buildModal() {
        const m = document.createElement('div');
        m.id = 'hn-egg-modal';
        m.innerHTML = '<div id="hn-egg-modal-inner">' +
            '<span id="hn-egg-modal-close">×</span>' +
            '<iframe id="hn-egg-iframe" src="/webagent/index.html" allow="microphone; camera"></iframe>' +
            '</div>';
        document.body.appendChild(m);
        document.getElementById('hn-egg-modal-close').addEventListener('click', closeModal);
        m.addEventListener('click', function(e) { if (e.target === m) closeModal(); });
        return m;
    }

    let tickerOpen = false;
    let modalOpen = false;
    let ticker, modal;

    function openTicker()  { tickerOpen = true;  ticker.classList.add('hn-active'); }
    function closeTicker() { tickerOpen = false; ticker.classList.remove('hn-active'); }
    function openModal()   { modalOpen = true;   modal.classList.add('hn-active'); }
    function closeModal()  { modalOpen = false;  modal.classList.remove('hn-active'); }

    function init() {
        ticker = buildTicker();
        modal  = buildModal();

        document.addEventListener('keydown', function(evt) {
            const tag = document.activeElement ? document.activeElement.tagName : '';
            if (['INPUT','TEXTAREA','SELECT'].includes(tag)) return;

            if (evt.key === 'e' || evt.key === 'E') {
                tickerOpen ? closeTicker() : openTicker();
            } else if (evt.key === 'a' || evt.key === 'A') {
                modalOpen ? closeModal() : openModal();
            } else if (evt.key === 'Escape') {
                closeTicker(); closeModal();
            }
        });
    }

    // Wait for body to be ready
    if (document.body) { init(); }
    else { document.addEventListener('DOMContentLoaded', init); }
}
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

        with gr.Blocks(title=f"HearthNet — {display_name}", css=_EASTER_EGG_RAW_CSS, js=_EASTER_EGG_JS) as demo:
            # Ticker & modal are created by JS appending to document.body (no HTML needed here)

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
