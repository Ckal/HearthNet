import importlib
import inspect
import json
import math
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import gradio as gr

try:
    import spaces
except ImportError:

    class _SpacesFallback:
        @staticmethod
        def GPU(  # pylint: disable=invalid-name
            *_args: object, **_kwargs: object
        ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
            def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
                return func

            return decorator

    spaces = _SpacesFallback()

APP_TITLE = "HearthNet"
APP_SUBTITLE = "Phase 1 browser-mesh coordination, resilient AI assistance, and traceable local-first workflows."


@spaces.GPU(duration=1)
def zero_gpu_startup_probe() -> str:
    return "HearthNet ZeroGPU probe ready"


@dataclass
class CoreAdapter:
    name: str
    module: Any | None
    error: str | None = None

    @property
    def available(self) -> bool:
        return self.module is not None


def _load_optional_core() -> CoreAdapter:
    candidates = ("hearthnet",)
    errors: list[str] = []
    for name in candidates:
        try:
            return CoreAdapter(name=name, module=importlib.import_module(name))
        except Exception as exc:
            errors.append(f"{name}: {exc.__class__.__name__}")
    return CoreAdapter(
        name="demo", module=None, error=", ".join(errors) or "No Python core discovered."
    )


CORE = _load_optional_core()


NODES = [
    {"id": "home-hub", "role": "coordinator", "status": "online", "latency": 12, "load": 42},
    {"id": "kitchen-panel", "role": "edge display", "status": "online", "latency": 19, "load": 24},
    {"id": "workbench", "role": "rag worker", "status": "online", "latency": 31, "load": 67},
    {
        "id": "phone-relay",
        "role": "emergency uplink",
        "status": "standby",
        "latency": 48,
        "load": 18,
    },
    {
        "id": "market-node",
        "role": "local marketplace",
        "status": "online",
        "latency": 27,
        "load": 39,
    },
]

TRACE_EVENTS = [
    ("intent", "Classify request and safety envelope"),
    ("route", "Select local RAG, mesh peer, or emergency path"),
    ("retrieve", "Pull local knowledge snippets and trusted marketplace records"),
    ("synthesize", "Draft answer with cited memory fragments"),
    ("verify", "Attach confidence, failover state, and operator next step"),
]


def _now() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _call_core(names: tuple[str, ...], fallback: Callable[[], Any]) -> Any:
    if not CORE.available:
        return fallback()
    for name in names:
        target = getattr(CORE.module, name, None)
        if callable(target):
            try:
                return target()
            except Exception:
                break
    return fallback()


def core_status() -> tuple[str, str]:
    if CORE.available:
        return (
            "Core linked",
            f"Using optional Python module `{CORE.name}`. Demo fallbacks remain active for missing hooks.",
        )
    return (
        "Demo mode",
        "No optional HearthNet Python core was importable, so this Space is running polished Phase 1 fixtures.",
    )


def overview_payload() -> tuple[str, str, str]:
    status, detail = core_status()
    capabilities = _call_core(
        ("get_capabilities", "capabilities", "status"),
        lambda: {
            "mesh": "WebRTC-ready topology model",
            "rag": "Local knowledge retrieval demo",
            "marketplace": "Neighborhood offer and request board",
            "chat": "Operator chat with emergency escalation",
            "trace": "Architecture event trail",
        },
    )
    health = {
        "phase": "1",
        "mode": status,
        "nodes": len(NODES),
        "online": sum(1 for node in NODES if node["status"] == "online"),
        "last_tick": _now(),
    }
    return detail, json.dumps(health, indent=2), json.dumps(capabilities, indent=2, default=str)


def topology_html(seed: int = 0) -> str:
    rnd = random.Random(seed or int(time.time() // 8))  # nosec B311 - visual jitter only.
    nodes = []
    for index, node in enumerate(NODES):
        angle = (index / len(NODES)) * 6.283
        jitter = rnd.uniform(-10, 10)
        x = 50 + 34 * math.cos(angle) + jitter * 0.12
        y = 52 + 30 * math.sin(angle) + jitter * 0.12
        pulse = max(8, min(92, int(str(node["load"])) + rnd.randint(-6, 6)))
        nodes.append({**node, "x": round(x, 2), "y": round(y, 2), "pulse": pulse})

    edges = [
        ("home-hub", "kitchen-panel"),
        ("home-hub", "workbench"),
        ("home-hub", "phone-relay"),
        ("home-hub", "market-node"),
        ("workbench", "market-node"),
    ]
    by_id = {node["id"]: node for node in nodes}
    lines = "\n".join(
        f"<line x1='{by_id[a]['x']}%' y1='{by_id[a]['y']}%' x2='{by_id[b]['x']}%' y2='{by_id[b]['y']}%' />"
        for a, b in edges
    )
    dot_parts = []
    for node in nodes:
        node_x = float(str(node["x"]))
        node_y = float(str(node["y"]))
        dot_parts.append(
            f"""
        <g>
          <circle class="node {node["status"]}" cx="{node_x}%" cy="{node_y}%" r="16" />
          <text x="{node_x}%" y="{node_y - 5}%" text-anchor="middle">{node["id"]}</text>
          <text class="meta" x="{node_x}%" y="{node_y + 5}%" text-anchor="middle">{node["latency"]}ms / {node["pulse"]}%</text>
        </g>
        """
        )
    dots = "\n".join(dot_parts)
    return f"""
    <div class="mesh-shell">
      <svg viewBox="0 0 100 100" preserveAspectRatio="xMidYMid meet" role="img" aria-label="HearthNet topology">
        <defs>
          <filter id="softGlow"><feGaussianBlur stdDeviation="0.7" result="blur"/><feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
        </defs>
        <rect x="0" y="0" width="100" height="100" rx="3" />
        <g class="links">{lines}</g>
        <g class="nodes" filter="url(#softGlow)">{dots}</g>
      </svg>
    </div>
    """


def mesh_snapshot(refresh_count: int) -> tuple[str, str, int]:
    next_count = refresh_count + 1
    rows = []
    for node in NODES:
        rows.append(
            {
                "node": node["id"],
                "role": node["role"],
                "state": node["status"],
                "latency_ms": int(str(node["latency"])) + (next_count % 4),
                "load_pct": max(
                    5,
                    min(95, int(str(node["load"])) + ((next_count % 3) - 1) * 3),
                ),
            }
        )
    return topology_html(next_count), json.dumps(rows, indent=2), next_count


def rag_answer(question: str, mode: str) -> tuple[str, str]:
    question = (question or "").strip()
    if not question:
        return "Ask a question to run the retrieval demo.", "[]"

    snippets = [
        {
            "source": "mesh.handbook.local",
            "score": 0.91,
            "text": "Home-hub coordinates browser peers, keeps the trace log, and chooses local fallbacks first.",
        },
        {
            "source": "emergency.playbook.local",
            "score": 0.86,
            "text": "Emergency mode prioritizes short instructions, phone relay status, and explicit escalation state.",
        },
        {
            "source": "marketplace.cache.local",
            "score": 0.78,
            "text": "Marketplace cards are signed local offers with expiry, distance, and trust metadata.",
        },
    ]
    prefix = "Core-assisted" if CORE.available else "Demo"
    answer = (
        f"{prefix} {mode.lower()} response for: {question}\n\n"
        "HearthNet would answer from local memory first, then ask mesh peers for missing context. "
        "For Phase 1 this Space shows the routing contract, citations, and confidence surface without requiring a heavy model."
    )
    if CORE.available:
        responder = getattr(CORE.module, "answer", None) or getattr(CORE.module, "query", None)
        if callable(responder):
            try:
                answer = str(responder(question))
            except Exception as exc:
                answer += f"\n\nCore hook failed gracefully: {exc.__class__.__name__}."
    return answer, json.dumps(snippets, indent=2)


def operator_chat(
    message: str, history: list[tuple[str, str]], emergency: bool
) -> tuple[list[tuple[str, str]], str]:
    history = history or []
    message = (message or "").strip()
    if not message:
        return history, ""

    if emergency:
        reply = (
            "Emergency mode is active. I would keep this terse: confirm immediate safety, surface the phone relay, "
            "and preserve a trace entry for every operator action."
        )
    elif "market" in message.lower() or "offer" in message.lower():
        reply = (
            "Marketplace view: 3 local offers match the current household context. "
            "Best candidate is `market-node` with fresh trust metadata and a 2 hour expiry."
        )
    else:
        reply = (
            "I routed that through the household coordinator. The next Phase 1 action is to retrieve local context, "
            "ask one mesh peer for corroboration, then return an auditable answer."
        )

    history = [*history, (message, reply)]
    return history, ""


def marketplace_cards(emergency: bool) -> str:
    cards = [
        ("Power bank", "phone-relay", "available now", "92% trust"),
        ("Spare router", "workbench", "pickup window 18:00-20:00", "88% trust"),
        ("First-aid kit", "kitchen-panel", "household verified", "96% trust"),
    ]
    if emergency:
        cards.insert(
            0, ("Emergency contact relay", "phone-relay", "priority path armed", "verified")
        )
    return "\n".join(
        f"- **{name}** · {node} · {detail} · `{trust}`" for name, node, detail, trust in cards
    )


def architecture_trace(intent: str) -> tuple[str, str]:
    intent = (intent or "Explain how HearthNet routes a request.").strip()
    events = []
    for index, (stage, label) in enumerate(TRACE_EVENTS, start=1):
        events.append(
            {
                "t": f"{_now()}.{index:02d}",
                "stage": stage,
                "event": label,
                "input": intent if index == 1 else f"artifact:{TRACE_EVENTS[index - 2][0]}",
                "output": f"{stage}.ok",
            }
        )
    diagram = "\n".join(f"{item['stage']:>10}  ->  {item['output']}" for item in events)
    return f"```text\n{diagram}\n```", json.dumps(events, indent=2)


CSS = """
:root {
  --hn-bg: #0b0d10;
  --hn-panel: #12161b;
  --hn-panel-2: #181e24;
  --hn-line: #26313b;
  --hn-text: #e4e9ee;
  --hn-muted: #8c99a5;
  --hn-accent: #54d1b6;
  --hn-warn: #e0b15f;
}
.gradio-container {
  max-width: 1180px !important;
  margin: 0 auto !important;
  background: var(--hn-bg) !important;
  color: var(--hn-text) !important;
}
body, .gradio-container, button, input, textarea {
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif !important;
}
#hero {
  padding: 26px 0 12px;
  border-bottom: 1px solid var(--hn-line);
  margin-bottom: 18px;
}
#hero h1 {
  margin: 0;
  font-size: clamp(34px, 6vw, 68px);
  line-height: 0.95;
  letter-spacing: 0;
}
#hero p {
  max-width: 760px;
  color: var(--hn-muted);
  font-size: 16px;
}
.hn-kicker {
  color: var(--hn-accent);
  font: 600 12px ui-monospace, SFMono-Regular, Menlo, monospace;
  letter-spacing: .12em;
  text-transform: uppercase;
}
.mesh-shell {
  height: min(56vw, 520px);
  min-height: 340px;
  border: 1px solid var(--hn-line);
  background: #090c0f;
  overflow: hidden;
}
.mesh-shell svg {
  width: 100%;
  height: 100%;
  display: block;
}
.mesh-shell rect {
  fill: #090c0f;
}
.mesh-shell line {
  stroke: #30404b;
  stroke-width: .45;
}
.mesh-shell .node {
  fill: #121b22;
  stroke: var(--hn-accent);
  stroke-width: .55;
}
.mesh-shell .node.standby {
  stroke: var(--hn-warn);
}
.mesh-shell text {
  fill: var(--hn-text);
  font: 2.6px ui-monospace, SFMono-Regular, Menlo, monospace;
}
.mesh-shell text.meta {
  fill: var(--hn-muted);
  font-size: 2.1px;
}
.wrap, .block, .form {
  border-radius: 8px !important;
}
button.primary {
  background: var(--hn-accent) !important;
  color: #06110f !important;
}
"""


def build_app() -> gr.Blocks:
    blocks_kwargs: dict[str, Any] = {"title": APP_TITLE}
    blocks_params = inspect.signature(gr.Blocks).parameters
    if "css" in blocks_params:
        blocks_kwargs["css"] = CSS
    if "theme" in blocks_params:
        blocks_kwargs["theme"] = gr.themes.Base()

    with gr.Blocks(**blocks_kwargs) as demo:
        refresh_state = gr.State(0)
        gr.HTML(
            f"""
            <div id="hero">
              <div class="hn-kicker">Phase 1 Space UI</div>
              <h1>{APP_TITLE}</h1>
              <p>{APP_SUBTITLE}</p>
            </div>
            """
        )

        with gr.Tabs():
            with gr.Tab("Overview"):
                gr.Markdown("### System Posture")
                with gr.Row():
                    core_detail = gr.Markdown()
                    health_json = gr.Code(label="Health", language="json")
                capabilities_json = gr.Code(label="Capabilities", language="json")
                overview_btn = gr.Button("Refresh Overview", variant="primary")
                overview_btn.click(
                    overview_payload, outputs=[core_detail, health_json, capabilities_json]
                )

            with gr.Tab("Live Mesh"):
                mesh_html = gr.HTML()
                with gr.Row():
                    mesh_json = gr.Code(label="Peer Snapshot", language="json")
                mesh_btn = gr.Button("Tick Topology", variant="primary")
                mesh_btn.click(
                    mesh_snapshot,
                    inputs=[refresh_state],
                    outputs=[mesh_html, mesh_json, refresh_state],
                )

            with gr.Tab("AI / RAG Demo"):
                with gr.Row():
                    question = gr.Textbox(
                        label="Question",
                        value="How should HearthNet respond if the internet is unavailable?",
                        lines=4,
                    )
                    mode = gr.Radio(
                        ["Local RAG", "Mesh Assisted", "Emergency Brief"],
                        label="Route",
                        value="Local RAG",
                    )
                ask_btn = gr.Button("Run Retrieval", variant="primary")
                answer = gr.Textbox(label="Answer", lines=8)
                citations = gr.Code(label="Retrieved Context", language="json")
                ask_btn.click(rag_answer, inputs=[question, mode], outputs=[answer, citations])

            with gr.Tab("Marketplace / Chat / Emergency"):
                emergency = gr.Checkbox(label="Emergency Mode", value=False)
                market = gr.Markdown()
                emergency.change(marketplace_cards, inputs=[emergency], outputs=[market])
                chatbot = gr.Chatbot(label="Operator Chat", height=320)
                chat_box = gr.Textbox(
                    label="Message",
                    placeholder="Ask about an offer, a neighbor node, or an emergency workflow.",
                )
                chat_box.submit(
                    operator_chat,
                    inputs=[chat_box, chatbot, emergency],
                    outputs=[chatbot, chat_box],
                )

            with gr.Tab("Architecture Trace"):
                trace_intent = gr.Textbox(
                    label="Intent",
                    value="A resident asks for help finding a verified first-aid kit during an outage.",
                    lines=3,
                )
                trace_btn = gr.Button("Generate Trace", variant="primary")
                trace_diagram = gr.Markdown()
                trace_json = gr.Code(label="Trace Events", language="json")
                trace_btn.click(
                    architecture_trace, inputs=[trace_intent], outputs=[trace_diagram, trace_json]
                )

        demo.load(overview_payload, outputs=[core_detail, health_json, capabilities_json])
        demo.load(
            mesh_snapshot, inputs=[refresh_state], outputs=[mesh_html, mesh_json, refresh_state]
        )
        demo.load(marketplace_cards, inputs=[emergency], outputs=[market])
        demo.load(architecture_trace, inputs=[trace_intent], outputs=[trace_diagram, trace_json])

    return demo


def launch_demo() -> None:
    launch_kwargs: dict[str, Any] = {}
    launch_params = inspect.signature(gr.Blocks.launch).parameters
    if "css" in launch_params:
        launch_kwargs["css"] = CSS
    if "theme" in launch_params:
        launch_kwargs["theme"] = gr.themes.Base()
    demo.launch(**launch_kwargs)


demo = build_app()


if __name__ == "__main__":
    launch_demo()
