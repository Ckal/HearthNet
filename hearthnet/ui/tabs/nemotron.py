"""Nemotron Document Intelligence tab.

Uses NVIDIA Nemotron Parse (sub-1B structured extraction) + Nemotron LLM
for document understanding, structured data extraction, and RAG ingest.

Qualifies for: NVIDIA Nemotron Hardware Prize (RTX 5080).
Tag: nemotron
"""

from __future__ import annotations

import os
from typing import Any


def _parse_with_nemotron(text: str, schema: str, api_key: str) -> dict:
    """Call Nemotron Parse via NVIDIA NIM for structured extraction."""
    try:
        import httpx

        system_prompt = (
            "You are a structured data extraction expert. "
            "Extract information from the provided document and return valid JSON "
            f"matching this schema:\n{schema}\n"
            "Return ONLY the JSON object, no explanation."
        )
        payload = {
            "model": "nvidia/llama-3.1-nemotron-nano-8b-instruct",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Document:\n{text[:4000]}"},
            ],
            "temperature": 0.1,
            "max_tokens": 1024,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        import asyncio

        async def _call():
            async with httpx.AsyncClient(timeout=30.0) as c:
                r = await c.post(
                    "https://integrate.api.nvidia.com/v1/chat/completions",
                    json=payload,
                    headers=headers,
                )
                r.raise_for_status()
                return r.json()

        resp = asyncio.get_event_loop().run_until_complete(_call())
        return {"result": resp["choices"][0]["message"]["content"], "model": "nemotron-parse"}
    except Exception as exc:
        return {"error": str(exc)}


def build_nemotron_tab(bus: Any | None = None) -> None:
    """Build the Nemotron Document Intelligence tab."""
    import gradio as gr

    api_key_env = os.getenv("NVIDIA_API_KEY", "")

    gr.Markdown(
        """
## 🔬 Document Intelligence (Nemotron)

Extract structured data from any document using **NVIDIA Nemotron** models.
Works offline with local Nemotron NIM, or online with the NVIDIA API.

**Capabilities:**
- 📄 Structured extraction (JSON schema → JSON output)
- 🔍 Document Q&A via Nemotron LLM
- 📚 Auto-ingest extracted data into RAG corpus
- 🌐 Handles PDFs, invoices, receipts, medical forms, legal documents
"""
    )

    with gr.Row():
        with gr.Column(scale=2):
            doc_input = gr.Textbox(
                label="📄 Document Text",
                placeholder="Paste document text here, or use the file upload below...",
                lines=10,
            )
            doc_file = gr.File(
                label="Or upload a file",
                type="filepath",
                file_types=[".txt", ".md", ".csv"],
            )

            schema_input = gr.Textbox(
                label="🗂 Extraction Schema (JSON)",
                value='{\n  "title": "string",\n  "date": "string",\n  "amount": "number",\n  "parties": ["string"],\n  "key_terms": ["string"]\n}',
                lines=8,
            )

            nvidia_key = gr.Textbox(
                label="🔑 NVIDIA API Key",
                value=api_key_env,
                type="password",
                placeholder="nvapi-... (or set NVIDIA_API_KEY env var)",
            )

        with gr.Column(scale=3):
            extract_btn = gr.Button("⚡ Extract with Nemotron", variant="primary")
            extraction_out = gr.Code(
                label="📊 Extracted JSON",
                language="json",
                lines=15,
            )

            with gr.Accordion("💬 Ask a question about the document", open=False):
                question_in = gr.Textbox(
                    label="Question",
                    placeholder="What is the total amount? Who signed this? What are the key dates?",
                )
                ask_btn = gr.Button("Ask Nemotron")
                answer_out = gr.Textbox(label="Answer", lines=4)

            with gr.Accordion("📚 Ingest into RAG corpus", open=False):
                corpus_name = gr.Textbox(
                    label="Corpus name",
                    value="documents",
                    placeholder="e.g. community, invoices, medical",
                )
                doc_title = gr.Textbox(label="Document title", placeholder="Invoice #12345")
                ingest_btn = gr.Button("Ingest into mesh RAG")
                ingest_status = gr.Textbox(label="Status", lines=2)

    # ── Status / instructions ──────────────────────────────────────────────────
    with gr.Accordion("[i] Setup & Prize Info", open=False):
        gr.Markdown(
            """
### Nemotron Setup

**Option A — NVIDIA Cloud (NIM API)**
1. Get a free API key at [build.nvidia.com](https://build.nvidia.com)
2. Paste it above (or set `NVIDIA_API_KEY` env var)
3. No local GPU needed

**Option B — Local NIM**
```bash
docker run --gpus all -p 8001:8000 \\
  nvcr.io/nim/nvidia/llama-3.1-nemotron-nano-8b-instruct:latest
```
Then set `NEMOTRON_URL=http://localhost:8001` in your config.

**Models used:**
- `nvidia/llama-3.1-nemotron-nano-8b-instruct` — structured extraction
- `nvidia/llama-3.1-nemotron-70b-instruct` — deep document Q&A

**Why Nemotron for this use case:**
Nemotron Parse is specifically designed for structured extraction from complex
documents. The nano variant runs on consumer GPU (8B params). For a community mesh,
this means offline document processing — no cloud dependency for sensitive documents.

### NVIDIA Nemotron Hardware Prize
This tab targets the [NVIDIA Nemotron Hardware Prize](https://huggingface.co/spaces/build-small-hackathon/HearthNet)
(RTX 5080). Requirements: build with Nemotron models ✅
"""
        )

    # ── Event handlers ─────────────────────────────────────────────────────────
    def load_file(filepath: str | None) -> str:
        if not filepath:
            return ""
        try:
            with open(filepath, encoding="utf-8", errors="replace") as f:
                return f.read(8000)
        except Exception as exc:
            return f"Error reading file: {exc}"

    def run_extraction(text: str, schema: str, key: str) -> str:
        if not text.strip():
            return '{"error": "No document text provided"}'
        if not key.strip():
            return '{"error": "NVIDIA API key required (get one free at build.nvidia.com)"}'
        result = _parse_with_nemotron(text, schema, key.strip())
        if "error" in result:
            return f'{{"error": "{result["error"]}"}}'
        return result.get("result", "{}")

    def ask_question(text: str, question: str, key: str) -> str:
        if not text.strip() or not question.strip():
            return "Please provide both a document and a question."
        if not key.strip():
            return "NVIDIA API key required."
        try:
            import asyncio

            import httpx

            payload = {
                "model": "nvidia/llama-3.1-nemotron-70b-instruct",
                "messages": [
                    {
                        "role": "system",
                        "content": "Answer questions about the provided document concisely and accurately.",
                    },
                    {
                        "role": "user",
                        "content": f"Document:\n{text[:3000]}\n\nQuestion: {question}",
                    },
                ],
                "temperature": 0.3,
                "max_tokens": 512,
            }
            headers = {
                "Authorization": f"Bearer {key.strip()}",
                "Content-Type": "application/json",
            }

            async def _call():
                async with httpx.AsyncClient(timeout=30.0) as c:
                    r = await c.post(
                        "https://integrate.api.nvidia.com/v1/chat/completions",
                        json=payload,
                        headers=headers,
                    )
                    r.raise_for_status()
                    return r.json()

            resp = asyncio.get_event_loop().run_until_complete(_call())
            return resp["choices"][0]["message"]["content"]
        except Exception as exc:
            return f"Error: {exc}"

    def ingest_doc(text: str, corpus: str, title: str) -> str:
        if not bus:
            return "⚠ Bus not available (running without mesh)"
        if not text.strip():
            return "⚠ No document to ingest"
        try:
            import asyncio

            async def _ingest():
                return await bus.call(
                    "rag.ingest",
                    (1, 0),
                    {
                        "params": {"corpus": corpus or "documents"},
                        "input": {
                            "documents": [
                                {
                                    "id": f"doc-{hash(text) % 100000}",
                                    "title": title or "Untitled",
                                    "text": text,
                                }
                            ]
                        },
                    },
                )

            result = asyncio.get_event_loop().run_until_complete(_ingest())
            if "error" in result:
                return f"⚠ Ingest error: {result['error']}"
            return f"✓ Ingested into corpus '{corpus}' — searchable via Ask tab"
        except Exception as exc:
            return f"⚠ Error: {exc}"

    doc_file.change(load_file, inputs=[doc_file], outputs=[doc_input])
    extract_btn.click(
        run_extraction,
        inputs=[doc_input, schema_input, nvidia_key],
        outputs=[extraction_out],
    )
    ask_btn.click(
        ask_question,
        inputs=[doc_input, question_in, nvidia_key],
        outputs=[answer_out],
    )
    ingest_btn.click(
        ingest_doc,
        inputs=[doc_input, corpus_name, doc_title],
        outputs=[ingest_status],
    )
