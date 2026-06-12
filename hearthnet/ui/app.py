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

            # Easter egg: press 'e' to toggle live news ticker overlay
            gr.HTML(value="""
            <style>
                .egg-ticker {
                    position: fixed;
                    bottom: 0;
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
                    transform: translateY(110%);
                    transition: transform 0.3s ease;
                    box-shadow: 0 -2px 10px rgba(0,0,0,0.5);
                }
                .egg-ticker.visible {
                    transform: translateY(0);
                }
                .egg-ticker.hidden {
                    transform: translateY(110%);
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
                @media (max-width: 768px) {
                    .egg-ticker { height: 50px; font-size: 12px; }
                    .egg-label { margin-right: 10px; }
                }
            </style>
            <div id="egg-ticker" class="egg-ticker hidden">
                <div class="egg-label">⚡ LIVE</div>
                <div id="egg-track" class="egg-track">
                    <span class="etk"><b>HearthNet</b> Press e to toggle ticker</span>
                </div>
            </div>
            <script>
                (function() {
                    let easterEggOpen = false;
                    const ticker = document.getElementById('egg-ticker');
                    const track = document.getElementById('egg-track');
                    
                    // Listen for 'e' key press globally
                    document.addEventListener('keydown', function(evt) {
                        if (evt.key === 'e' || evt.key === 'E') {
                            // Don't trigger if typing in an input
                            const focused = document.activeElement;
                            if (focused && (focused.tagName === 'INPUT' || focused.tagName === 'TEXTAREA' || focused.contentEditable === 'true')) {
                                return;
                            }
                            easterEggOpen = !easterEggOpen;
                            if (ticker) {
                                ticker.classList.remove('hidden');
                                ticker.classList.toggle('visible', easterEggOpen);
                                if (easterEggOpen) {
                                    populateEgg();
                                }
                            }
                        }
                    });
                    
                    // Populate ticker with headlines from news sources
                    async function populateEgg() {
                        if (!track) return;
                        try {
                            // Try to fetch headlines (simplified version)
                            track.innerHTML = '<span class="etk"><b>BleepingComputer</b> Security Updates</span>' +
                                            '<span class="etk"><b>Reuters</b> World News</span>' +
                                            '<span class="etk"><b>TechCrunch</b> Latest Updates</span>' +
                                            '<span class="etk"><b>BBC</b> Breaking News</span>' +
                                            '<span class="etk"><b>AP News</b> Top Stories</span>';
                        } catch (e) {
                            console.error('Easter egg fetch failed:', e);
                        }
                    }
                })();
            </script>
            """)

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
