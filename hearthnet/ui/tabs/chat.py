"""Direct chat tab — event-sourced peer-to-peer messaging via the bus (M10)."""

from __future__ import annotations


def build_chat_tab(bus=None):
    import gradio as gr

    my_node_id = getattr(bus, "node_id_full", None) if bus else None

    with gr.Column():
        gr.Markdown("""### 💬 Direct Messages

Send and receive messages between HearthNet nodes (M10).
Messages are **event-sourced** with Lamport clocks — delivery order is deterministic
even when nodes reconnect after an offline period.
""")

        if my_node_id:
            gr.Markdown(
                f"**Your Node ID** (share this so others can message you):\n\n"
                f"```\n{my_node_id}\n```"
            )

        gr.Markdown("""
**How to use:**
1. Enter a **Recipient Node ID** — copy it from their Settings tab
2. Click **Load History** to see past messages
3. Type a message and press **Send**

**Send to all peers:** use `*` as the recipient to broadcast to every known peer.

**Delivery status:**
- `direct` — sent to yourself (same node)
- `queued` — stored locally, will deliver when recipient reconnects
- `delivered` — recipient on a live peer node acknowledged receipt

> On the **HF Space** (single node): only self-messages (`direct`) work.
> For real peer messaging, run two local nodes — see Getting Started.
""")

        with gr.Row():
            peer_id = gr.Textbox(
                label="Recipient Node ID",
                placeholder=f"e.g. {my_node_id or 'ed25519:...'}  (use * for broadcast)",
                scale=4,
            )
            history_btn = gr.Button("Load History", scale=1)

        chat_out = gr.Chatbot(label="Messages", height=340)

        with gr.Row():
            msg_input = gr.Textbox(label="Message", placeholder="Type a message…", scale=7)
            send_btn = gr.Button("Send", scale=1, variant="primary")

        status_out = gr.Markdown(visible=False)

        async def load_history(peer):
            if bus is None:
                return [{"role": "assistant", "content": "⚠️ Bus not connected"}]
            target = peer.strip() if peer else None
            try:
                r = await bus.call("chat.history", (1, 0), {"input": {"peer": target}})
                msgs = r.get("output", {}).get("messages", [])
                if not msgs:
                    return [{"role": "assistant", "content": "(no messages yet)"}]
                result = []
                node_me = getattr(bus, "node_id_full", "me")
                for m in msgs:
                    sender = m.get("from", "?")
                    is_mine = sender == node_me
                    result.append(
                        {
                            "role": "user" if is_mine else "assistant",
                            "content": f"{'You' if is_mine else sender}: {m.get('body', '')}",
                        }
                    )
                return result
            except Exception as e:
                return [{"role": "assistant", "content": f"Error loading history: {e}"}]

        async def send_msg(peer, msg, history):
            if not msg.strip():
                return history, "", gr.update(visible=False)
            history = history or []
            if bus is None:
                return (
                    [
                        *history,
                        {"role": "user", "content": msg},
                        {"role": "assistant", "content": "⚠️ Bus not connected"},
                    ],
                    "",
                    gr.update(visible=False),
                )

            # Broadcast to all peers if * used
            recipient = peer.strip() if peer else getattr(bus, "node_id_full", "")
            if recipient == "*":
                # Send to all known peers
                peers_snapshot = getattr(bus, "topology_snapshot", lambda: None)()
                all_peers = [p.get("node_id") for p in (getattr(peers_snapshot, "peers", []) or [])]
                if not all_peers:
                    all_peers = [getattr(bus, "node_id_full", recipient)]
                results = []
                for p in all_peers:
                    try:
                        r = await bus.call(
                            "chat.send", (1, 0), {"input": {"recipient": p, "body": msg}}
                        )
                        results.append(r.get("output", {}).get("delivered", "queued"))
                    except Exception:
                        results.append("error")
                history = [
                    *history,
                    {"role": "user", "content": f"[broadcast to {len(all_peers)} peers] {msg}"},
                ]
                note = f"✓ Broadcast sent to {len(all_peers)} peer(s): {results}"
                return history, "", gr.update(visible=True, value=note)

            try:
                r = await bus.call(
                    "chat.send", (1, 0), {"input": {"recipient": recipient, "body": msg}}
                )
                status = r.get("output", {}).get("delivered", "queued")
                history = [*history, {"role": "user", "content": msg}]
                if status == "direct":
                    # Self-message — also show it as received
                    history.append({"role": "assistant", "content": f"[echo] {msg}"})
                note = f"✓ {status} → `{recipient}`"
                return history, "", gr.update(visible=True, value=note)
            except Exception as e:
                history = [
                    *history,
                    {"role": "user", "content": msg},
                    {"role": "assistant", "content": f"Error: {e}"},
                ]
                return history, "", gr.update(visible=False)

        history_btn.click(load_history, inputs=peer_id, outputs=chat_out)
        send_btn.click(
            send_msg,
            inputs=[peer_id, msg_input, chat_out],
            outputs=[chat_out, msg_input, status_out],
        )
        msg_input.submit(
            send_msg,
            inputs=[peer_id, msg_input, chat_out],
            outputs=[chat_out, msg_input, status_out],
        )
