from __future__ import annotations

import html
import importlib
import inspect
import json
import math
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import gradio as gr

try:
    import spaces
except ImportError:

    def _gpu(
        *_args: object, **_kwargs: object
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            return func

        return decorator

    class _SpacesFallback:
        GPU = staticmethod(_gpu)

    spaces = _SpacesFallback()


APP_TITLE = "HearthNet"
APP_SUBTITLE = "Local-first community AI mesh. Real local models first, online APIs only by choice."

LOCAL_CORPUS = [
    {
        "source": "emergency.water.local",
        "title": "Water Safety",
        "text": (
            "If the mains supply is disrupted, use stored clean water first. Rainwater should be "
            "filtered through clean cloth, brought to a rolling boil for at least one minute, and "
            "stored in a clean covered container."
        ),
    },
    {
        "source": "emergency.power.local",
        "title": "Power Outage",
        "text": (
            "Keep refrigerators closed, disconnect sensitive devices, reserve battery banks for "
            "communication, and share verified charging points through the local marketplace."
        ),
    },
    {
        "source": "community.mesh.local",
        "title": "HearthNet Routing",
        "text": (
            "A HearthNet UI sends requests to a controller. The controller calls facades, facades "
            "call the capability bus, and the bus selects local or peer capabilities based on "
            "health, parameters, and trust."
        ),
    },
    {
        "source": "firstaid.basics.local",
        "title": "First Aid Basics",
        "text": (
            "Check scene safety, call local emergency contacts when available, assess breathing, "
            "control severe bleeding with direct pressure, and keep the person warm until help arrives."
        ),
    },
]

MODEL_PROFILES = {
    "SmolLM2 135M local": {
        "provider": "hf",
        "model_id": "HuggingFaceTB/SmolLM2-135M-Instruct",
        "revision": "12fd25f77366fa6b3b4b768ec3050bf629380bac",
        "trust_remote_code": False,
        "note": "Small default for fast local-first Space inference.",
    },
    "SmolLM2 360M local": {
        "provider": "hf",
        "model_id": "HuggingFaceTB/SmolLM2-360M-Instruct",
        "revision": "a10cc1512eabd3dde888204e902eca88bddb4951",
        "trust_remote_code": False,
        "note": "Better local answer quality, still lightweight.",
    },
    "OpenBMB MiniCPM local": {
        "provider": "hf",
        "model_id": "openbmb/MiniCPM-2B-sft-bf16",
        "revision": "4ec16344ac13e6ef5010aeecaa533369ac8eb53c",
        "trust_remote_code": True,
        "note": "OpenBMB small-model family. May need more memory and model-specific code.",
    },
    "NVIDIA Nemotron Nano local": {
        "provider": "hf",
        "model_id": "nvidia/Llama-3.1-Nemotron-Nano-8B-v1",
        "revision": "54641c1611fcff44fa4865626462445e0a153fc7",
        "trust_remote_code": True,
        "note": "Verified Nemotron Nano profile. Likely too large for free/light Space runtime.",
    },
    "OpenAI online fallback": {
        "provider": "openai",
        "model_id": os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        "revision": "",
        "trust_remote_code": False,
        "note": "Used only when explicitly selected and OPENAI_API_KEY is configured.",
    },
}

# Reference node roles for topology illustration (HF Space has no live bus)
# In a real node, topology is served from bus.registry.all_remote()
REFERENCE_TOPOLOGY = [
    {"id": "anchor-node", "role": "controller + bus", "status": "reference"},
    {"id": "rag-node", "role": "rag + local model", "status": "reference"},
    {"id": "thin-client", "role": "thin client", "status": "reference"},
    {"id": "bridge-node", "role": "optional internet relay", "status": "reference"},
]


@dataclass(frozen=True)
class RetrievalHit:
    source: str
    title: str
    text: str
    score: float


def _now() -> str:
    return time.strftime("%H:%M:%S")


def _terms(text: str) -> set[str]:
    return {part.strip(".,!?;:()[]{}").lower() for part in text.split() if len(part) > 2}


def retrieve_local_context(question: str, limit: int = 3) -> list[RetrievalHit]:
    query_terms = _terms(question)
    hits: list[RetrievalHit] = []
    for doc in LOCAL_CORPUS:
        doc_terms = _terms(f"{doc['title']} {doc['text']}")
        overlap = query_terms & doc_terms
        score = len(overlap) / max(len(query_terms), 1)
        hits.append(
            RetrievalHit(
                source=doc["source"],
                title=doc["title"],
                text=doc["text"],
                score=round(score, 3),
            )
        )
    return sorted(hits, key=lambda hit: hit.score, reverse=True)[:limit]


def build_prompt(question: str, hits: list[RetrievalHit], emergency: bool) -> str:
    mode = "emergency local mode" if emergency else "normal local-first mode"
    context = "\n".join(
        f"- {hit.title} ({hit.source}, score={hit.score}): {hit.text}" for hit in hits
    )
    return (
        "You are HearthNet, a local-first community AI assistant.\n"
        "Answer only from the local context when possible. Say when context is insufficient. "
        "Keep emergency advice concise and practical.\n\n"
        f"Mode: {mode}\n"
        f"Local context:\n{context}\n\n"
        f"Question: {question}\n"
        "Answer:"
    )


@lru_cache(maxsize=3)
def _load_hf_pipeline(model_id: str, revision: str, trust_remote_code: bool) -> Any:
    torch = importlib.import_module("torch")
    transformers = importlib.import_module("transformers")
    auto_tokenizer = transformers.AutoTokenizer
    auto_model = transformers.AutoModelForCausalLM
    pipeline = transformers.pipeline

    device = 0 if torch.cuda.is_available() else -1
    dtype = torch.float16 if torch.cuda.is_available() else torch.float32
    tokenizer = auto_tokenizer.from_pretrained(
        model_id, revision=revision, trust_remote_code=trust_remote_code
    )
    model = auto_model.from_pretrained(
        model_id,
        revision=revision,
        torch_dtype=dtype,
        trust_remote_code=trust_remote_code,
        low_cpu_mem_usage=True,
    )
    return pipeline("text-generation", model=model, tokenizer=tokenizer, device=device)


@spaces.GPU(duration=120)
def generate_with_local_model(
    prompt: str, model_id: str, revision: str, trust_remote_code: bool
) -> str:
    generator = _load_hf_pipeline(model_id, revision, trust_remote_code)
    result = generator(
        prompt,
        max_new_tokens=180,
        do_sample=False,
        return_full_text=False,
        pad_token_id=getattr(generator.tokenizer, "eos_token_id", None),
    )
    if not result:
        raise RuntimeError("local model returned no text")
    text = str(result[0].get("generated_text", "")).strip()
    if not text:
        raise RuntimeError("local model returned empty text")
    return text


def generate_with_openai(prompt: str, model_id: str) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")
    openai_module = importlib.import_module("openai")

    client = openai_module.OpenAI(api_key=api_key)
    response = client.responses.create(
        model=model_id,
        input=prompt,
        max_output_tokens=220,
    )
    return response.output_text.strip()


def answer_question(question: str, model_profile: str, emergency: bool) -> tuple[str, str, str]:
    question = question.strip()
    if not question:
        return "Ask a question first.", "[]", "No route selected."

    profile = MODEL_PROFILES[model_profile]
    hits = retrieve_local_context(question)
    prompt = build_prompt(question, hits, emergency)
    route = [
        "UI -> HearthNetController",
        "HearthNetController -> RagFacade",
        "RagFacade -> capability bus: rag.query@1.0",
        f"Capability bus -> local context: {', '.join(hit.source for hit in hits)}",
    ]
    try:
        if profile["provider"] == "openai":
            route.append("Online route explicitly selected -> OpenAI")
            answer = generate_with_openai(prompt, str(profile["model_id"]))
        else:
            route.append(f"Local model -> {profile['model_id']}")
            answer = generate_with_local_model(
                prompt,
                str(profile["model_id"]),
                str(profile["revision"]),
                bool(profile["trust_remote_code"]),
            )
    except Exception as exc:
        answer = (
            "Backend error. HearthNet did not fabricate an answer.\n\n"
            f"{exc.__class__.__name__}: {exc}"
        )
        route.append("generation failed -> surfaced real backend error")

    citations = [
        {"source": hit.source, "title": hit.title, "score": hit.score, "text": hit.text}
        for hit in hits
    ]
    return (
        answer,
        json.dumps(citations, indent=2),
        "\n".join(f"{i + 1}. {step}" for i, step in enumerate(route)),
    )


def chat_turn(
    message: str,
    history: list[tuple[str, str]],
    model_profile: str,
    emergency: bool,
) -> tuple[list[tuple[str, str]], str]:
    history = history or []
    message = message.strip()
    if not message:
        return history, ""
    answer, _, _ = answer_question(message, model_profile, emergency)
    return [*history, (message, answer)], ""


def topology_html(tick: int = 0) -> str:
    """Render reference topology for HF Space (no live bus).
    Real nodes show live topology via bus.registry.all_remote().
    """
    node_cards = []
    for index, node in enumerate(REFERENCE_TOPOLOGY):
        angle = (index / len(REFERENCE_TOPOLOGY)) * math.tau
        x = 50 + 34 * math.cos(angle + tick * 0.03)
        y = 50 + 26 * math.sin(angle + tick * 0.03)
        node_cards.append(
            f"""
            <g>
              <circle cx="{x:.2f}" cy="{y:.2f}" r="7.5" class="hn-node {node['status']}" />
              <text x="{x:.2f}" y="{y - 10:.2f}" text-anchor="middle">{html.escape(str(node['id']))}</text>
              <text x="{x:.2f}" y="{y + 12:.2f}" text-anchor="middle" class="hn-meta">{html.escape(str(node['role']))}</text>
            </g>
            """
        )
    label = "Reference topology (HF Space demo — run a real node for live mesh)"
    return f"""
    <section class="hn-topology">
      <p style="color:#888;font-size:10px;text-align:center">{label}</p>
      <svg viewBox="0 0 100 100" role="img" aria-label="HearthNet reference topology">
        <rect x="0" y="0" width="100" height="100" rx="2" />
        <line x1="50" y1="50" x2="84" y2="50" />
        <line x1="50" y1="50" x2="50" y2="76" />
        <line x1="50" y1="50" x2="16" y2="50" />
        <line x1="50" y1="50" x2="50" y2="24" />
        {"".join(node_cards)}
      </svg>
    </section>
    """


def mesh_snapshot(tick: int) -> tuple[str, str, int]:
    next_tick = tick + 1
    rows = [
        {"node": node["id"], "role": node["role"], "state": node["status"]}
        for node in REFERENCE_TOPOLOGY
    ]
    note = {"info": "HF Space shows reference topology only. Run a real node for live mesh data."}
    return topology_html(next_tick), json.dumps([note, *rows], indent=2), next_tick


def model_status(model_profile: str) -> str:
    profile = MODEL_PROFILES[model_profile]
    internet_state = "configured" if os.getenv("OPENAI_API_KEY") else "not configured"
    return (
        f"Provider: `{profile['provider']}`\n\n"
        f"Model: `{profile['model_id']}`\n\n"
        f"Revision: `{profile['revision'] or 'n/a'}`\n\n"
        f"Note: {profile['note']}\n\n"
        f"OpenAI key: `{internet_state}`"
    )


def marketplace_html() -> str:
    """Marketplace preview for HF Space.
    Real nodes show live posts via bus.call('market.list', ...).
    """
    return  """<div class='hn-card-grid'>
      <article class="hn-card">
        <span>how it works</span>
        <h3>Community Marketplace</h3>
        <p>Run a real HearthNet node to post and browse community offers, requests, and emergency resources.
        Posts are event-sourced and replicated across the mesh.</p>
      </article>
    </div>"""
    


def trace_html() -> str:
    steps = [
        ("System of concern", "community-owned resilient AI assistance"),
        ("Controller", "HearthNetController owns user flow and state"),
        ("Facades", "RAG/chat/marketplace interfaces hide bus calls"),
        ("Capability bus", "routes by capability, params, health, and trust"),
        ("Local model", "HF Transformers first, OpenAI only when selected online"),
    ]
    return (
        "<div class='hn-trace'>"
        + "".join(f"<div><b>{html.escape(k)}</b><p>{html.escape(v)}</p></div>" for k, v in steps)
        + "</div>"
    )


CSS = """
:root {
  --hn-bg: #08100f;
  --hn-panel: #101a18;
  --hn-panel-2: #162421;
  --hn-line: #2f4841;
  --hn-text: #e9f4ef;
  --hn-muted: #9fb5ad;
  --hn-accent: #69e0bb;
  --hn-warn: #f2c166;
}
.gradio-container {
  max-width: 1240px !important;
  margin: 0 auto !important;
  background: var(--hn-bg) !important;
  color: var(--hn-text) !important;
}
body, .gradio-container, button, input, textarea {
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif !important;
}
#hn-hero {
  min-height: 38vh;
  display: grid;
  align-items: end;
  padding: 40px 0 22px;
  border-bottom: 1px solid var(--hn-line);
  background:
    linear-gradient(90deg, rgba(8,16,15,.95), rgba(8,16,15,.5)),
    radial-gradient(circle at 80% 20%, rgba(105,224,187,.22), transparent 34%),
    linear-gradient(135deg, #08100f, #17211d 58%, #24352e);
}
#hn-hero h1 {
  margin: 0;
  font-size: clamp(42px, 8vw, 92px);
  line-height: .9;
  letter-spacing: 0;
}
#hn-hero p {
  color: var(--hn-muted);
  max-width: 760px;
  font-size: 17px;
}
.hn-kicker {
  color: var(--hn-accent);
  font: 700 12px ui-monospace, SFMono-Regular, Menlo, monospace;
  letter-spacing: .14em;
  text-transform: uppercase;
}
.hn-topology {
  min-height: 430px;
  border: 1px solid var(--hn-line);
  background: #07100e;
}
.hn-topology svg {
  width: 100%;
  height: 430px;
  display: block;
}
.hn-topology rect {
  fill: #07100e;
}
.hn-topology line {
  stroke: #42675d;
  stroke-width: .35;
}
.hn-node {
  fill: #10231f;
  stroke: var(--hn-accent);
  stroke-width: .6;
}
.hn-node.standby {
  stroke: var(--hn-warn);
}
.hn-topology text {
  fill: var(--hn-text);
  font: 2.4px ui-monospace, SFMono-Regular, Menlo, monospace;
}
.hn-topology .hn-meta {
  fill: var(--hn-muted);
  font-size: 1.9px;
}
.hn-card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
  gap: 12px;
}
.hn-card, .hn-trace > div {
  border: 1px solid var(--hn-line);
  background: var(--hn-panel);
  border-radius: 8px;
  padding: 14px;
}
.hn-card span {
  color: var(--hn-accent);
  font: 700 11px ui-monospace, SFMono-Regular, Menlo, monospace;
  text-transform: uppercase;
}
.hn-card h3 {
  margin: 8px 0 4px;
}
.hn-card p, .hn-trace p {
  color: var(--hn-muted);
  margin: 0;
}
.hn-trace {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
}
"""


def build_app() -> gr.Blocks:
    blocks_kwargs: dict[str, Any] = {"title": APP_TITLE}
    blocks_params = inspect.signature(gr.Blocks).parameters
    if "css" in blocks_params:
        blocks_kwargs["css"] = CSS
    if "theme" in blocks_params:
        blocks_kwargs["theme"] = gr.themes.Base()

    with gr.Blocks(**blocks_kwargs) as interface:
        tick = gr.State(0)
        gr.HTML(
            f"""
            <section id="hn-hero">
              <div>
                <div class="hn-kicker">HearthNet Phase 1 - local-first</div>
                <h1>{APP_TITLE}</h1>
                <p>{APP_SUBTITLE}</p>
              </div>
            </section>
            """
        )

        with gr.Row():
            model_profile = gr.Dropdown(
                choices=list(MODEL_PROFILES),
                value="SmolLM2 135M local",
                label="Inference route",
            )
            emergency = gr.Checkbox(label="Emergency local mode", value=False)

        model_info = gr.Markdown()
        model_profile.change(model_status, inputs=[model_profile], outputs=[model_info])

        with gr.Tabs():
            with gr.Tab("Ask"):
                question = gr.Textbox(
                    label="Question",
                    value="How should HearthNet respond if the internet is unavailable?",
                    lines=4,
                )
                ask_btn = gr.Button("Ask local-first model", variant="primary")
                answer = gr.Textbox(label="Model answer", lines=10)
                route = gr.Textbox(label="Capability route", lines=7)
                citations = gr.Code(label="Local context", language="json")
                ask_btn.click(
                    answer_question,
                    inputs=[question, model_profile, emergency],
                    outputs=[answer, citations, route],
                )

            with gr.Tab("Mesh"):
                mesh = gr.HTML()
                peer_json = gr.Code(label="Peer snapshot", language="json")
                mesh_btn = gr.Button("Refresh mesh", variant="primary")
                mesh_btn.click(mesh_snapshot, inputs=[tick], outputs=[mesh, peer_json, tick])

            with gr.Tab("Community"):
                gr.HTML(marketplace_html())
                chat = gr.Chatbot(label="Local-first operator chat", height=360)
                chat_box = gr.Textbox(label="Message")
                chat_box.submit(
                    chat_turn,
                    inputs=[chat_box, chat, model_profile, emergency],
                    outputs=[chat, chat_box],
                )

            with gr.Tab("Architecture"):
                gr.HTML(trace_html())
                gr.Markdown(
                    "This Space uses a real local HF model backend first. OpenAI is only used when "
                    "`OpenAI online fallback` is explicitly selected and an API key exists."
                )

        interface.load(model_status, inputs=[model_profile], outputs=[model_info])
        interface.load(mesh_snapshot, inputs=[tick], outputs=[mesh, peer_json, tick])

    return interface


demo = build_app()


def launch_demo() -> None:
    launch_kwargs: dict[str, Any] = {}
    launch_params = inspect.signature(gr.Blocks.launch).parameters
    if "server_port" in launch_params and os.getenv("PORT"):
        launch_kwargs["server_port"] = int(os.environ["PORT"])
    demo.launch(**launch_kwargs)


if __name__ == "__main__":
    launch_demo()
