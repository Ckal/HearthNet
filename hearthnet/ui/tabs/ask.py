"""Ask tab — LLM + RAG via capability bus.

The request flow is:
  UI → bus.call("rag.query") [optional, if corpus selected]
     → bus.call("llm.chat")  [routes to best available node]

The routing trace shows exactly which node answered and why.
No hardcoded responses. If no LLM is configured, an UnavailableBackend
error is surfaced directly rather than fabricating an answer.

Spec: docs/M04-llm.md, docs/M05-rag.md, docs/M03-bus.md §4
"""

from __future__ import annotations


def _msg_text(content) -> str:
    """Coerce Gradio chat-message content to a plain string.

    ``gr.Chatbot(type="messages")`` can round-trip content back as a structured
    list/dict (e.g. ``[{'text': '...'}]``). Flatten it so the LLM prompt never
    receives that structure verbatim.
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        return str(content.get("text") or content.get("content") or "")
    if isinstance(content, (list, tuple)):
        parts: list[str] = []
        for p in content:
            if isinstance(p, dict):
                parts.append(str(p.get("text") or p.get("content") or ""))
            elif isinstance(p, str):
                parts.append(p)
        return " ".join(x for x in parts if x).strip()
    return str(content)


def _get_corpora_sync(bus) -> list[str]:
    """Scan the bus registry synchronously for all rag.query corpus names.

    This is safe to call at build time (no event loop needed).
    """
    if bus is None:
        return []
    corpora: list[str] = []
    try:
        all_entries = list(bus.registry.all())
        for entry in all_entries:
            if entry.descriptor.name == "rag.query":
                corpus = (entry.descriptor.params or {}).get("corpus")
                if corpus and corpus not in corpora:
                    corpora.append(corpus)
    except Exception:
        pass
    return corpora


async def _get_corpora_async(bus) -> list[str]:
    """Fetch corpora via rag.list_corpora capability, falling back to registry scan."""
    if bus is None:
        return []
    try:
        r = await bus.call("rag.list_corpora", (1, 0), {"input": {}})
        corpora = r.get("output", {}).get("corpora", [])
        if corpora:
            return corpora
    except Exception:
        pass
    return _get_corpora_sync(bus)


# Backward compat alias used at module load
def _get_corpora(bus) -> list[str]:
    return _get_corpora_sync(bus)


def build_ask_tab(bus=None):
    import gradio as gr

    corpora = _get_corpora(bus)
    corpus_choices = ["(none)"] + corpora

    with gr.Column():
        gr.Markdown("""### 💬 Ask the Mesh

Send a question to the **HearthNet capability bus**. The bus routes the request
to the best available LLM node — either on this device or on a peer.

**How it works:**
- **(none) corpus** → question goes directly to the LLM
- **Select a corpus** → RAG retrieval runs first; top chunks become system context
- **Model: auto** → bus picks highest-scoring available node (local first, then peer)
- **Model: name** → routes only to nodes that advertise that exact model

**Routing is transparent** — the trace below every response shows which node answered.
""")

        with gr.Row():
            corpus_selector = gr.Dropdown(
                label="RAG Corpus (leave blank for direct LLM)",
                choices=corpus_choices,
                value=corpus_choices[0],
                scale=3,
            )
            model_selector = gr.Dropdown(
                label="Model (auto = bus picks best node)",
                choices=["auto"],
                value="auto",
                scale=2,
            )
            refresh_corpora_btn = gr.Button("🔄 Refresh Corpora", size="sm", scale=1)

        chatbot = gr.Chatbot(
            label="Conversation",
            height=440,
            show_label=True,
        )

        with gr.Row():
            msg_input = gr.Textbox(
                label="Your message",
                placeholder="e.g. What is HearthNet? / How do I filter rainwater? / List my neighbours' capabilities.",
                lines=2,
                scale=8,
            )
            send_btn = gr.Button("Send", scale=1, variant="primary")

        with gr.Row():
            sources_out = gr.JSON(label="📚 RAG Sources", visible=False, scale=2)
            route_out = gr.JSON(label="🛣️ Routing Trace", visible=False, scale=2)

        def refresh_corpora():
            choices = ["(none)"] + _get_corpora_sync(bus)
            return gr.update(choices=choices, value=choices[0])

        async def handle_send(message: str, history: list, corpus: str, model: str):
            if not message.strip():
                return history, "", gr.update(visible=False), gr.update(visible=False)

            history = history or []
            history.append({"role": "user", "content": message})

            if bus is None:
                history.append(
                    {
                        "role": "assistant",
                        "content": "⚠️ Bus not connected — run as a real HearthNet node.",
                    }
                )
                return history, "", gr.update(visible=False), gr.update(visible=False)

            trace: dict = {"rag": None, "llm": None, "routed_to": None}
            try:
                context = ""
                sources: list = []

                if corpus and corpus != "(none)":
                    try:
                        rag_result = await bus.call(
                            "rag.query",
                            (1, 0),
                            {
                                "params": {"corpus": corpus},
                                "input": {"query": message, "k": 3},
                            },
                        )
                        chunks = rag_result.get("output", {}).get("chunks", [])
                        routed_via_rag = rag_result.get("_routed_via", "local")
                        trace["rag"] = {
                            "capability": "rag.query",
                            "corpus": corpus,
                            "chunks_found": len(chunks),
                            "routed_via": routed_via_rag,
                        }
                        if chunks:
                            context = "\n\n".join(c["text"] for c in chunks[:3])
                            sources = [
                                {
                                    "rank": c.get("rank", i),
                                    "text": c["text"][:120],
                                    "source": c.get("metadata", {}).get("doc_title", "unknown"),
                                }
                                for i, c in enumerate(chunks)
                            ]
                    except Exception as rag_exc:
                        trace["rag"] = {"error": str(rag_exc)}

                llm_messages: list = []
                if context:
                    # Truncate RAG context to prevent prompt-injection via doc content (LLM01)
                    _safe_ctx = context[:4000].replace("\x00", "")
                    llm_messages.append({"role": "system", "content": f"Context:\n{_safe_ctx}"})
                llm_messages.extend(
                    {"role": h["role"], "content": _msg_text(h["content"])} for h in history
                )

                params: dict = {}
                if model and model != "auto":
                    params["model"] = model

                result = await bus.call(
                    "llm.chat",
                    (1, 0),
                    {"params": params, "input": {"messages": llm_messages}},
                )

                # Surface errors clearly instead of showing "No response"
                if "error" in result:
                    err_msg = result.get("message", result.get("error", "unknown error"))
                    reply = f"⚠️ LLM error: {err_msg}"
                    trace["llm"] = {"error": err_msg}
                else:
                    reply = (
                        result.get("output", {}).get("message", {}).get("content")
                        or result.get("output", {}).get("text")
                        or "(empty response — model may still be loading)"
                    )
                    routed_via_llm = result.get("_routed_via", "local")
                    trace["llm"] = {
                        "capability": "llm.chat",
                        "model_requested": model if model != "auto" else "(any)",
                        "routed_via": routed_via_llm,
                    }
                    trace["routed_to"] = routed_via_llm

                history.append({"role": "assistant", "content": reply})

                return (
                    history,
                    "",
                    gr.update(visible=bool(sources), value=sources),
                    gr.update(visible=True, value=trace),
                )

            except Exception as exc:
                history.append({"role": "assistant", "content": f"❌ Error: {exc}"})
                trace["error"] = str(exc)
                return (
                    history,
                    "",
                    gr.update(visible=False),
                    gr.update(visible=True, value=trace),
                )

        refresh_corpora_btn.click(refresh_corpora, outputs=corpus_selector)
        send_btn.click(
            handle_send,
            inputs=[msg_input, chatbot, corpus_selector, model_selector],
            outputs=[chatbot, msg_input, sources_out, route_out],
        )
        msg_input.submit(
            handle_send,
            inputs=[msg_input, chatbot, corpus_selector, model_selector],
            outputs=[chatbot, msg_input, sources_out, route_out],
        )
