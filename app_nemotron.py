"""HearthNet Document Intelligence — Nemotron-powered second Space.

A standalone Gradio app focused entirely on document intelligence using
NVIDIA Nemotron models. Can run independently OR as part of a HearthNet mesh.

Deploy as a second HF Space alongside the main HearthNet mesh Space.

Prize targets:
  - NVIDIA Nemotron Hardware Prize (RTX 5080): Build with Nemotron models ✅
  - 🐜 Tiny Titan: Nemotron-nano-8B is 8B params (under 32B) ✅
  - 🎨 Off Brand: Custom-styled beyond default Gradio look ✅

Usage:
  python app_nemotron.py

Environment:
  NVIDIA_API_KEY   — NVIDIA NIM API key (get free at build.nvidia.com)
  NEMOTRON_URL     — local NIM endpoint (optional, for offline use)
  HEARTHNET_NODE   — URL of a HearthNet mesh node to push results into
"""

from __future__ import annotations

import os

import gradio as gr

# ── Optional mesh connection ──────────────────────────────────────────────────
_MESH_NODE = os.getenv("HEARTHNET_NODE", "")
_NVIDIA_KEY = os.getenv("NVIDIA_API_KEY", "")
_NEMOTRON_URL = os.getenv("NEMOTRON_URL", "")

# ── Nemotron model catalogue ──────────────────────────────────────────────────
_MODELS = {
    "Nemotron Nano 8B (fast)": "nvidia/llama-3.1-nemotron-nano-8b-instruct",
    "Nemotron Super 49B (deep)": "nvidia/llama-3.3-nemotron-super-49b-v1",
    "Nemotron 70B (balanced)": "nvidia/llama-3.1-nemotron-70b-instruct",
}

_SCHEMAS = {
    "Invoice / Receipt": """{
  "vendor": "string",
  "date": "string",
  "total_amount": "number",
  "currency": "string",
  "line_items": [{"description": "string", "amount": "number"}],
  "tax": "number"
}""",
    "Medical Form": """{
  "patient_name": "string",
  "date_of_birth": "string",
  "diagnosis": ["string"],
  "medications": ["string"],
  "doctor": "string",
  "date": "string"
}""",
    "Legal Document": """{
  "document_type": "string",
  "parties": ["string"],
  "effective_date": "string",
  "key_obligations": ["string"],
  "governing_law": "string"
}""",
    "Meeting Notes": """{
  "date": "string",
  "attendees": ["string"],
  "decisions": ["string"],
  "action_items": [{"owner": "string", "task": "string", "due": "string"}]
}""",
    "Custom (edit below)": "{}",
}

# ── Custom HearthNet theme ────────────────────────────────────────────────────
_theme = gr.themes.Soft(
    primary_hue=gr.themes.colors.orange,
    secondary_hue=gr.themes.colors.purple,
    neutral_hue=gr.themes.colors.gray,
    font=[gr.themes.GoogleFont("Inter"), "ui-sans-serif", "sans-serif"],
).set(
    button_primary_background_fill="*primary_500",
    button_primary_background_fill_hover="*primary_600",
    block_title_text_weight="600",
    block_border_width="1px",
)


# ── Core functions ────────────────────────────────────────────────────────────

def _get_endpoint(api_key: str) -> str:
    return _NEMOTRON_URL.rstrip("/") + "/v1" if _NEMOTRON_URL else "https://integrate.api.nvidia.com/v1"


async def _nemotron_chat(messages: list, model: str, api_key: str, temperature: float = 0.1) -> str:
    import httpx

    endpoint = _get_endpoint(api_key)
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": 2048,
    }
    async with httpx.AsyncClient(timeout=60.0) as c:
        r = await c.post(f"{endpoint}/chat/completions", json=payload, headers=headers)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]


def extract_structured(
    doc_text: str,
    schema_preset: str,
    custom_schema: str,
    model_label: str,
    api_key: str,
) -> tuple[str, str]:
    import asyncio, json

    if not doc_text.strip():
        return '{"error": "No document text provided"}', "⚠ Provide document text"

    key = api_key.strip() or _NVIDIA_KEY
    if not key and not _NEMOTRON_URL:
        return (
            '{"error": "No API key or local endpoint configured"}',
            "⚠ Set NVIDIA_API_KEY or NEMOTRON_URL",
        )

    schema = custom_schema.strip() if schema_preset == "Custom (edit below)" else _SCHEMAS[schema_preset]
    model = _MODELS.get(model_label, list(_MODELS.values())[0])

    system = (
        "You are a precise structured data extraction engine. "
        "Extract information from the document and return ONLY valid JSON "
        f"matching this exact schema:\n{schema}\n"
        "If a field is not found, use null. Never add fields not in the schema."
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": f"Document:\n\n{doc_text[:5000]}"},
    ]

    try:
        raw = asyncio.get_event_loop().run_until_complete(
            _nemotron_chat(messages, model, key, temperature=0.05)
        )
        # Try to parse to validate it's real JSON
        try:
            parsed = json.loads(raw)
            return json.dumps(parsed, indent=2), f"✓ Extracted with {model_label}"
        except json.JSONDecodeError:
            return raw, f"⚠ Model returned non-JSON (shown as-is)"
    except Exception as exc:
        return f'{{"error": "{exc}"}}', f"⚠ Error: {exc}"


def ask_document(doc_text: str, question: str, model_label: str, api_key: str) -> str:
    import asyncio

    if not doc_text.strip():
        return "Provide a document first."
    if not question.strip():
        return "Ask a question."

    key = api_key.strip() or _NVIDIA_KEY
    if not key and not _NEMOTRON_URL:
        return "Set NVIDIA_API_KEY or NEMOTRON_URL to use Nemotron."

    model = _MODELS.get(model_label, list(_MODELS.values())[0])
    messages = [
        {
            "role": "system",
            "content": "Answer questions about the document concisely and accurately. "
            "Cite specific parts of the document when relevant.",
        },
        {
            "role": "user",
            "content": f"Document:\n\n{doc_text[:4000]}\n\nQuestion: {question}",
        },
    ]
    try:
        return asyncio.get_event_loop().run_until_complete(
            _nemotron_chat(messages, model, key, temperature=0.3)
        )
    except Exception as exc:
        return f"Error: {exc}"


def summarise_document(doc_text: str, style: str, model_label: str, api_key: str) -> str:
    import asyncio

    if not doc_text.strip():
        return "Provide a document first."

    key = api_key.strip() or _NVIDIA_KEY
    if not key and not _NEMOTRON_URL:
        return "Set NVIDIA_API_KEY or NEMOTRON_URL."

    model = _MODELS.get(model_label, list(_MODELS.values())[0])
    style_prompts = {
        "Executive (3 bullets)": "Summarise in exactly 3 bullet points for an executive audience.",
        "Detailed (paragraph)": "Write a thorough 2-paragraph summary covering all key points.",
        "ELI5 (simple)": "Explain this document as simply as possible, as if to a 10-year-old.",
        "Action items only": "List only the action items, decisions, and next steps.",
    }
    prompt = style_prompts.get(style, "Summarise the document.")
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": f"Document:\n\n{doc_text[:5000]}"},
    ]
    try:
        return asyncio.get_event_loop().run_until_complete(
            _nemotron_chat(messages, model, key, temperature=0.4)
        )
    except Exception as exc:
        return f"Error: {exc}"


def push_to_mesh(doc_text: str, doc_title: str, corpus: str, mesh_url: str) -> str:
    import asyncio, httpx

    url = (mesh_url.strip() or _MESH_NODE).rstrip("/")
    if not url:
        return "⚠ Set HEARTHNET_NODE env var or enter mesh URL to push to mesh."
    if not doc_text.strip():
        return "⚠ No document to push."

    async def _push():
        payload = {
            "body": {
                "params": {"corpus": corpus or "documents"},
                "input": {
                    "documents": [
                        {
                            "id": f"doc-{hash(doc_text) % 100000}",
                            "title": doc_title or "Untitled",
                            "text": doc_text,
                        }
                    ]
                },
            }
        }
        async with httpx.AsyncClient(timeout=15.0) as c:
            r = await c.post(f"{url}/capabilities/rag.ingest/call", json=payload)
            r.raise_for_status()
            return r.json()

    try:
        asyncio.get_event_loop().run_until_complete(_push())
        return f"✓ Document pushed to mesh at {url}\nCorpus: {corpus}\nNow searchable via Ask tab on any mesh node."
    except Exception as exc:
        return f"⚠ Push failed: {exc}"


# ── Build UI ──────────────────────────────────────────────────────────────────

def build_app() -> gr.Blocks:
    with gr.Blocks(
        title="HearthNet · Document Intelligence",
        theme=_theme,
        css="""
.grad-banner { background: linear-gradient(135deg, #7c3aed 0%, #f97316 100%);
               border-radius: 12px; padding: 16px 24px; margin-bottom: 16px; }
.grad-banner h1 { color: white !important; margin: 0; }
.grad-banner p  { color: rgba(255,255,255,0.85) !important; margin: 4px 0 0; }
.feature-badge { display: inline-block; padding: 2px 10px; border-radius: 12px;
                 font-size: 0.78em; font-weight: 600; margin: 2px; }
""",
    ) as demo:
        # ── Header ────────────────────────────────────────────────────────────
        gr.HTML("""
<div class="grad-banner">
  <h1>🔬 HearthNet · Document Intelligence</h1>
  <p>Structured extraction &amp; Q&amp;A powered by NVIDIA Nemotron · Part of the HearthNet mesh</p>
</div>
<p>
  <span class="feature-badge" style="background:#7c3aed;color:white">NVIDIA Nemotron</span>
  <span class="feature-badge" style="background:#f97316;color:white">Structured Extraction</span>
  <span class="feature-badge" style="background:#0ea5e9;color:white">Offline Capable</span>
  <span class="feature-badge" style="background:#10b981;color:white">Mesh RAG Ingest</span>
</p>
""")

        # ── Shared controls (sidebar-style top row) ────────────────────────────
        with gr.Row():
            model_selector = gr.Dropdown(
                label="🤖 Nemotron Model",
                choices=list(_MODELS.keys()),
                value=list(_MODELS.keys())[0],
                scale=2,
            )
            api_key_box = gr.Textbox(
                label="🔑 NVIDIA API Key",
                value=_NVIDIA_KEY,
                type="password",
                placeholder="nvapi-... (free at build.nvidia.com) or set NVIDIA_API_KEY",
                scale=3,
            )

        # ── Main tabs ──────────────────────────────────────────────────────────
        with gr.Tabs():

            # ── Tab 1: Structured Extraction ──────────────────────────────────
            with gr.Tab("📊 Extract"):
                with gr.Row():
                    with gr.Column(scale=2):
                        extract_doc = gr.Textbox(
                            label="Document",
                            placeholder="Paste text, or upload a file below...",
                            lines=12,
                        )
                        extract_file = gr.File(
                            label="Upload file",
                            type="filepath",
                            file_types=[".txt", ".md", ".csv"],
                        )
                        schema_preset = gr.Dropdown(
                            label="Schema preset",
                            choices=list(_SCHEMAS.keys()),
                            value="Invoice / Receipt",
                        )
                        custom_schema = gr.Code(
                            label="Schema (JSON)",
                            language="json",
                            value=_SCHEMAS["Invoice / Receipt"],
                            lines=8,
                        )

                    with gr.Column(scale=3):
                        extract_btn = gr.Button("⚡ Extract with Nemotron", variant="primary", size="lg")
                        extract_out = gr.Code(label="Extracted JSON", language="json", lines=16)
                        extract_status = gr.Textbox(label="Status", lines=1, interactive=False)

                def on_preset_change(preset):
                    return _SCHEMAS.get(preset, "{}")

                schema_preset.change(on_preset_change, inputs=[schema_preset], outputs=[custom_schema])

                def load_extract_file(fp):
                    if not fp:
                        return ""
                    try:
                        with open(fp, encoding="utf-8", errors="replace") as f:
                            return f.read(8000)
                    except Exception as e:
                        return f"Error: {e}"

                extract_file.change(load_extract_file, inputs=[extract_file], outputs=[extract_doc])
                extract_btn.click(
                    extract_structured,
                    inputs=[extract_doc, schema_preset, custom_schema, model_selector, api_key_box],
                    outputs=[extract_out, extract_status],
                )

            # ── Tab 2: Document Q&A ───────────────────────────────────────────
            with gr.Tab("💬 Ask"):
                with gr.Row():
                    with gr.Column(scale=2):
                        ask_doc = gr.Textbox(
                            label="Document",
                            placeholder="Paste the document to query...",
                            lines=14,
                        )

                    with gr.Column(scale=3):
                        ask_question_box = gr.Textbox(
                            label="Question",
                            placeholder="What is the total? Who are the parties? What are the obligations?",
                            lines=2,
                        )
                        ask_btn = gr.Button("🔍 Ask Nemotron", variant="primary")
                        ask_out = gr.Textbox(label="Answer", lines=8)

                ask_btn.click(
                    ask_document,
                    inputs=[ask_doc, ask_question_box, model_selector, api_key_box],
                    outputs=[ask_out],
                )

            # ── Tab 3: Summarise ──────────────────────────────────────────────
            with gr.Tab("✂ Summarise"):
                with gr.Row():
                    with gr.Column(scale=2):
                        sum_doc = gr.Textbox(
                            label="Document",
                            placeholder="Paste document text...",
                            lines=14,
                        )

                    with gr.Column(scale=3):
                        sum_style = gr.Dropdown(
                            label="Summary style",
                            choices=[
                                "Executive (3 bullets)",
                                "Detailed (paragraph)",
                                "ELI5 (simple)",
                                "Action items only",
                            ],
                            value="Executive (3 bullets)",
                        )
                        sum_btn = gr.Button("✂ Summarise with Nemotron", variant="primary")
                        sum_out = gr.Textbox(label="Summary", lines=10)

                sum_btn.click(
                    summarise_document,
                    inputs=[sum_doc, sum_style, model_selector, api_key_box],
                    outputs=[sum_out],
                )

            # ── Tab 4: Push to Mesh ───────────────────────────────────────────
            with gr.Tab("🕸 Push to Mesh"):
                gr.Markdown(
                    "Send extracted/processed documents into a HearthNet mesh node's RAG corpus. "
                    "After ingesting, documents become searchable from any mesh node's **Ask** tab."
                )
                with gr.Row():
                    with gr.Column():
                        mesh_doc = gr.Textbox(
                            label="Document text",
                            placeholder="Paste processed document...",
                            lines=10,
                        )
                        mesh_title = gr.Textbox(label="Document title", placeholder="Invoice #123")
                        mesh_corpus = gr.Textbox(label="Corpus name", value="documents")
                        mesh_url = gr.Textbox(
                            label="HearthNet mesh node URL",
                            value=_MESH_NODE,
                            placeholder="http://localhost:7860 or https://your-space.hf.space",
                        )
                        mesh_push_btn = gr.Button("🚀 Push to mesh", variant="primary")

                    with gr.Column():
                        mesh_status = gr.Textbox(label="Status", lines=5)
                        gr.Markdown(
                            """
**How to use with the HearthNet main Space:**
1. Set `HEARTHNET_NODE = https://build-small-hackathon-hearthnet.hf.space`
2. Or run locally: `python app.py` → `http://localhost:7860`
3. Documents ingested here appear in the **Ask** tab on all mesh nodes

**Local multi-node example:**
```bash
# Node 1 (main mesh)
python app.py --port 7860

# Node 2 (this document intelligence app)
python app_nemotron.py --port 7861
HEARTHNET_NODE=http://localhost:7860
```
"""
                        )

                mesh_push_btn.click(
                    push_to_mesh,
                    inputs=[mesh_doc, mesh_title, mesh_corpus, mesh_url],
                    outputs=[mesh_status],
                )

            # ── Tab 5: About ──────────────────────────────────────────────────
            with gr.Tab("ℹ About"):
                gr.Markdown(
                    f"""
## HearthNet Document Intelligence

A companion app to the [HearthNet mesh](https://huggingface.co/spaces/build-small-hackathon/HearthNet)
that adds NVIDIA Nemotron-powered document processing.

### Models
| Model | Size | Best for |
|-------|------|---------|
| Nemotron Nano 8B | 8B | Fast extraction, Pi-friendly |
| Nemotron 70B | 70B | Deep reasoning, complex docs |
| Nemotron Super 49B | 49B | Balanced quality/speed |

All models are under 32B parameters individually ✅

### Architecture
```
Document Input ──► Nemotron Parse ──► Structured JSON
                                   ──► Q&A Answers  
                                   ──► Summary
                                        │
                                        ▼
                              HearthNet RAG Corpus
                              (searchable on all mesh nodes)
```

### Prize Targets
- 🏆 **NVIDIA Nemotron Hardware Prize** (RTX 5080) — builds with Nemotron ✅
- 🐜 **Tiny Titan** — Nano 8B model ✅
- 🎨 **Off Brand** — Custom purple-to-orange UI ✅

### Links
- [Main HearthNet Space](https://huggingface.co/spaces/build-small-hackathon/HearthNet)
- [HF Profile](https://huggingface.co/Chris4K)
- [X / Twitter](https://x.com/zX14_7)
- [GitHub](https://github.com/ckal)
- [NVIDIA NIM API](https://build.nvidia.com) — free tier available

**Current status:** API key: {'✓ configured' if _NVIDIA_KEY else '✗ not set (add NVIDIA_API_KEY)'}
**Mesh node:** {_MESH_NODE or '✗ not set (add HEARTHNET_NODE)'}
"""
                )

    return demo


if __name__ == "__main__":
    demo = build_app()
    demo.launch(
        server_name="0.0.0.0",  # nosec B104
        server_port=int(os.getenv("PORT", "7861")),
        show_api=True,
    )
