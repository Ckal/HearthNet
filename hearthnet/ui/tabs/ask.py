"""Ask tab: LLM passthrough with optional RAG."""
from __future__ import annotations


def build_ask_tab(bus=None):
    import gradio as gr

    with gr.Column():
        gr.Markdown("### Ask the Mesh")
        gr.Markdown("*Query is routed to the best available LLM/RAG node.*")

        with gr.Row():
            corpus_selector = gr.Dropdown(
                label="RAG Corpus (optional)",
                choices=["(none)"],
                value="(none)",
                scale=2,
            )
            model_selector = gr.Dropdown(
                label="Model",
                choices=["auto"],
                value="auto",
                scale=2,
            )

        chatbot = gr.Chatbot(label="Conversation", height=400)

        with gr.Row():
            msg_input = gr.Textbox(
                label="Message",
                placeholder="Ask anything...",
                lines=2,
                scale=8,
            )
            send_btn = gr.Button("Send", scale=1, variant="primary")

        sources_out = gr.JSON(label="Sources", visible=False)

        async def handle_send(message: str, history: list, corpus: str, model: str):
            if not message.strip():
                return history, "", gr.update(visible=False), []

            # Gradio 6: messages are dicts with role/content
            history = history or []
            history.append({"role": "user", "content": message})

            if bus is None:
                history.append({"role": "assistant", "content": "⚠️ Bus not connected. Running in demo mode."})
                return history, "", gr.update(visible=False), []

            try:
                # Optional RAG context
                context = ""
                sources = []
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
                        if chunks:
                            context = "\n\n".join(c["text"] for c in chunks[:3])
                            sources = [
                                {
                                    "rank": c["rank"],
                                    "text": c["text"][:100],
                                    "source": c.get("metadata", {}).get("doc_title", ""),
                                }
                                for c in chunks
                            ]
                    except Exception:
                        pass

                # Build messages for LLM (use history)
                llm_messages = []
                if context:
                    llm_messages.append({"role": "system", "content": f"Context:\n{context}"})
                for h in history:
                    llm_messages.append({"role": h["role"], "content": h["content"]})

                params = {}
                if model and model != "auto":
                    params["model"] = model

                result = await bus.call(
                    "llm.chat",
                    (1, 0),
                    {"params": params, "input": {"messages": llm_messages}},
                )
                reply = (
                    result.get("output", {}).get("message", {}).get("content", "No response")
                )
                history.append({"role": "assistant", "content": reply})

                return history, "", gr.update(visible=bool(sources), value=sources), sources

            except Exception as exc:
                history.append({"role": "assistant", "content": f"Error: {exc}"})
                return history, "", gr.update(visible=False), []

        send_btn.click(
            handle_send,
            inputs=[msg_input, chatbot, corpus_selector, model_selector],
            outputs=[chatbot, msg_input, sources_out, sources_out],
        )
        msg_input.submit(
            handle_send,
            inputs=[msg_input, chatbot, corpus_selector, model_selector],
            outputs=[chatbot, msg_input, sources_out, sources_out],
        )
