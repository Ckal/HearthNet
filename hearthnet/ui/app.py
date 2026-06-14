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


# Ticker HTML — track is populated at runtime via JS from live APIs
_EGG_HTML = """
<div class="hn-ticker">
  <span class="hn-lbl">⚡ LIVE</span>
  <div class="hn-track">
    <span class="hn-item"><b>Loading</b> — fetching live headlines…</span>
  </div>
</div>
<div class="hn-modal">
  <div class="hn-modal-box">
    <button class="hn-close" title="Close (Esc)">x</button>
    <iframe class="hn-iframe" src="/webagent/index.html" allow="microphone; camera"></iframe>
  </div>
</div>
"""

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
            .hn-track { display: flex; animation: hn-scroll 80s linear infinite; white-space: nowrap; }
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
            if (ticker.classList.contains('hn-on')) _hnFetchNews(ticker);
        } else if (evt.key === 'a' || evt.key === 'A') {
            modal.classList.toggle('hn-on');
        } else if (evt.key === 'Escape') {
            ticker.classList.remove('hn-on');
            modal.classList.remove('hn-on');
        }
    });

    // ── Typed-sequence reveal: type "hearthnet" anywhere to open the agent ──
    let _hnBuf = '';
    document.addEventListener('keydown', evt => {
        const tag = (document.activeElement || {}).tagName || '';
        if (['INPUT', 'TEXTAREA', 'SELECT'].includes(tag)) return;
        if (evt.key && evt.key.length === 1) {
            _hnBuf = (_hnBuf + evt.key.toLowerCase()).slice(-9);
            if (_hnBuf === 'hearthnet') {
                _hnBuf = '';
                modal.classList.add('hn-on');
            }
        }
    });

    // ── Live news fetch (HN + BBC via CORS proxy) ───────────────────────────
    function _hnEsc(s) {
        return String(s || '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
    }
    function _hnRenderTrack(items) {
        const track = ticker.querySelector('.hn-track');
        if (!track || !items.length) return;
        const spans = items.map(i =>
            `<span class="hn-item"><b>${_hnEsc(i.s)}</b> — ${_hnEsc(i.t)}</span>`
        ).join('');
        track.innerHTML = spans + spans;  // doubled for seamless loop
    }
    async function _hnFetchNews(ticker) {
        // Guard: only fetch once
        if (ticker._newsFetched) return;
        ticker._newsFetched = true;
        const items = [];
        // 1) Hacker News top stories (no proxy needed, JSON API)
        try {
            const ids = await fetch('https://hacker-news.firebaseio.com/v0/topstories.json').then(r => r.json());
            const stories = await Promise.all(
                ids.slice(0, 12).map(id =>
                    fetch(`https://hacker-news.firebaseio.com/v0/item/${id}.json`).then(r => r.json())
                )
            );
            for (const s of stories) {
                if (s?.title) items.push({ s: s.score > 99 ? '🔥 HN' : 'HN', t: s.title });
            }
        } catch(e) {}
        // 2) BBC World via allorigins CORS proxy
        try {
            const proxy = 'https://api.allorigins.win/get?url=';
            const feed = 'https://feeds.bbci.co.uk/news/world/rss.xml';
            const j = await fetch(proxy + encodeURIComponent(feed)).then(r => r.json());
            const doc = new DOMParser().parseFromString(j.contents || '', 'text/xml');
            for (const it of [...doc.querySelectorAll('item')].slice(0, 8)) {
                const t = it.querySelector('title')?.textContent?.trim();
                if (t) items.push({ s: 'BBC', t });
            }
        } catch(e) {}
        if (items.length) _hnRenderTrack(items);
    }
"""


class UiApp:
    def __init__(self, bus=None, state_bus=None, config=None, node=None, **meta):
        self._bus = bus
        self._state_bus = state_bus
        self._config = config
        self._node = node
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
                    build_mesh_tab(self._bus, node=self._node)
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


def build_ui(bus, state_bus=None, config=None, node=None, **meta) -> UiApp:
    """Convenience constructor used by node.py."""
    return UiApp(bus=bus, state_bus=state_bus, config=config, node=node, **meta)
