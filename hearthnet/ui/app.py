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
        from hearthnet.ui.tabs.image import build_image_tab
        from hearthnet.ui.tabs.marketplace import build_marketplace_tab
        from hearthnet.ui.tabs.mesh import build_mesh_tab
        from hearthnet.ui.tabs.nemotron import build_nemotron_tab
        from hearthnet.ui.tabs.ocr import build_ocr_tab
        from hearthnet.ui.tabs.settings import build_settings_tab
        from hearthnet.ui.tabs.translation import build_translation_tab
        from hearthnet.ui.tabs.voice import build_voice_tab

        # Pull identity from bus when not explicitly provided in meta
        if self._bus is not None:
            self._meta.setdefault("node_id", getattr(self._bus, "node_id_full", "unknown"))
            self._meta.setdefault("community_id", getattr(self._bus, "community_id", "unknown"))

        from hearthnet.ui.theme import hearthnet_theme

        node_id_display = self._meta.get("node_id", "unknown")
        display_name = self._meta.get("display_name", node_id_display[:20])

        _css = """
/* HearthNet custom UI */
.hn-header {
    background: linear-gradient(135deg, #7c3aed 0%, #1e40af 60%, #0f172a 100%);
    border-radius: 14px; padding: 20px 28px; margin-bottom: 12px;
    border: 1px solid #7c3aed44;
    box-shadow: 0 4px 24px rgba(124,58,237,.25);
}
.hn-header h1 { color: #fff !important; margin: 0; font-size: 1.6em; }
.hn-header p  { color: rgba(255,255,255,.75) !important; margin: 4px 0 0; font-size: .9em; }
.hn-badge {
    display: inline-block; padding: 3px 11px; border-radius: 14px;
    font-size: .72em; font-weight: 700; margin: 2px 3px;
    letter-spacing: .03em;
}
.hn-status-row { display: flex; align-items: center; gap: 16px;
    background: #d2d8e8; border-radius: 8px; padding: 8px 16px;
    border: 1px solid #7c3aed33; margin-bottom: 8px; }
.hn-dot { display: inline-block; width: 9px; height: 9px;
    border-radius: 50%; background: #22c55e;
    box-shadow: 0 0 6px #22c55e; animation: hn-pulse 2s infinite; }
@keyframes hn-pulse { 0%,100%{opacity:1} 50%{opacity:.5} }
.hn-node-id { font-family: monospace; font-size:.8em; color:#94a3b8; }
/* Tab bar polish */
.tab-nav button { border-radius: 8px 8px 0 0 !important; font-weight: 600; }
/* Button hover animation */
.gr-button-primary { transition: transform .1s, box-shadow .1s; }
.gr-button-primary:hover { transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(124,58,237,.4); }
"""

        with gr.Blocks(
            title=f"HearthNet — {display_name}",
            theme=hearthnet_theme,
            css=_css,
        ) as demo:
            # Easter egg ticker + agent modal via Gradio 6 js_on_load API
            gr.HTML(html_template=_EGG_HTML, js_on_load=_EGG_JS)

            gr.HTML(f"""
<div class="hn-header">
  <h1>🔥 HearthNet — {display_name}</h1>
  <p>Community AI mesh · offline-first · P2P capability routing</p>
</div>
<div style="margin-bottom:8px">
  <span class="hn-badge" style="background:#7c3aed;color:#fff">MiniCPM3-4B</span>
  <span class="hn-badge" style="background:#1e40af;color:#fff">NVIDIA Nemotron</span>
  <span class="hn-badge" style="background:#0f766e;color:#fff">RAG</span>
  <span class="hn-badge" style="background:#b45309;color:#fff">Offline-First</span>
  <span class="hn-badge" style="background:#7c3aed44;color:#c4b5fd;border:1px solid #7c3aed">P2P Mesh</span>
</div>
""")

            with gr.Row():
                gr.HTML(value=f"""<div class="hn-status-row">
  <span class="hn-dot"></span>
  <span style="color:#22c55e;font-weight:700">ONLINE</span>
  <span class="hn-node-id">Node: {node_id_display[:44]}</span>
  <span class="hn-node-id" style="margin-left:auto">Community: {self._meta.get('community_id','unknown')[:34]}</span>
</div>""")

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
                with gr.Tab("🔬 Nemotron"):
                    build_nemotron_tab(self._bus)
                with gr.Tab("🎙 Voice"):
                    build_voice_tab(self._bus)
                with gr.Tab("🖼 Image"):
                    build_image_tab(self._bus)
                with gr.Tab("📄 OCR"):
                    build_ocr_tab(self._bus)
                with gr.Tab("🌍 Translation"):
                    build_translation_tab(self._bus)
                with gr.Tab("Emergency"):
                    build_emergency_tab(self._bus, self._state_bus)
                with gr.Tab("Settings"):
                    _rag_svc = getattr(self._node, "_rag_service", None)
                    build_settings_tab(self._config, self._meta, bus=self._bus, rag_service=_rag_svc)
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
