"""Chat tab."""
from __future__ import annotations


def build_chat_tab(bus=None):
    import gradio as gr

    with gr.Column():
        gr.Markdown("### Direct Messages")

        with gr.Row():
            peer_id = gr.Textbox(
                label="Recipient Node ID", placeholder="ed25519:...", scale=4
            )
            history_btn = gr.Button("Load History", scale=1)

        chat_out = gr.Chatbot(label="Messages", height=300)

        with gr.Row():
            msg_input = gr.Textbox(label="Message", scale=7)
            send_btn = gr.Button("Send", scale=1, variant="primary")
        send_result = gr.JSON(visible=False)

        async def load_history(peer):
            if bus is None:
                return [{"role": "assistant", "content": "Bus not connected"}]
            try:
                r = await bus.call(
                    "chat.history", (1, 0), {"input": {"peer": peer or None}}
                )
                msgs = r.get("output", {}).get("messages", [])
                result = []
                for m in msgs:
                    result.append({"role": "user", "content": f"[{m.get('from','?')}]: {m.get('body','')}" })
                return result
            except Exception as e:
                return [{"role": "assistant", "content": f"Error: {e}"}]

        async def send_msg(peer, msg, history):
            if not peer or not msg:
                return history, "", gr.update(visible=False)
            history = history or []
            if bus is None:
                history = history + [{"role": "user", "content": msg}, {"role": "assistant", "content": "⚠️ Bus not connected"}]
                return history, "", gr.update(visible=False)
            try:
                r = await bus.call(
                    "chat.send",
                    (1, 0),
                    {"input": {"recipient": peer, "body": msg}},
                )
                status = r.get("output", {}).get("delivered", "sent")
                history = history + [
                    {"role": "user", "content": msg},
                    {"role": "assistant", "content": f"✓ delivered={status}"},
                ]
                return history, "", gr.update(visible=True, value=r.get("output"))
            except Exception as e:
                history = history + [{"role": "user", "content": msg}, {"role": "assistant", "content": f"Error: {e}"}]
        history_btn.click(load_history, inputs=peer_id, outputs=chat_out)
        send_btn.click(
            send_msg,
            inputs=[peer_id, msg_input, chat_out],
            outputs=[chat_out, msg_input, send_result],
        )
