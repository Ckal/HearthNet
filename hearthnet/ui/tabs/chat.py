"""Direct chat tab — event-sourced peer-to-peer messaging via the bus (M10)."""

from __future__ import annotations


def _get_known_peers(bus) -> list[str]:
    """Return node IDs of all remote peers currently in the registry."""
    if bus is None:
        return []
    try:
        seen: set[str] = set()
        for entry in bus.registry.all_remote():
            nid = entry.node_id
            if nid and nid not in seen:
                seen.add(nid)
        return sorted(seen)
    except Exception:
        return []


def build_chat_tab(bus=None):
    import gradio as gr

    my_node_id = getattr(bus, "node_id_full", None) if bus else None
    initial_peers = _get_known_peers(bus)

    with gr.Column():
        gr.Markdown("### 💬 Direct Messages")

        if my_node_id:
            gr.Markdown(
                f"**Your Node ID** (share this so others can message you):\n\n"
                f"```\n{my_node_id}\n```"
            )

        gr.Markdown(
            "> **Cross-node chat requires 2 nodes.** "
            "Open the **Mesh** tab, click **Join Relay**, then come back here "
            "and click **🔄 Refresh Peers** to see who's online.\n\n"
            "> To start a second local node: `python scripts/start_mesh_node.py --name Bob --port 7081 --connect hf --demo-services`"
        )

        with gr.Row():
            peer_dropdown = gr.Dropdown(
                label="Known peers (from relay)",
                choices=initial_peers,
                value=initial_peers[0] if initial_peers else None,
                interactive=True,
                allow_custom_value=True,
                scale=4,
            )
            refresh_peers_btn = gr.Button("🔄 Refresh Peers", size="sm", scale=1)

        with gr.Row():
            peer_id = gr.Textbox(
                label="Recipient Node ID (paste here or pick above)",
                placeholder=f"e.g. {my_node_id or 'ed25519:...'}  (use * for broadcast)",
                scale=4,
            )
            history_btn = gr.Button("Load History", scale=1)

        # Clicking a peer in the dropdown fills the text box
        peer_dropdown.change(lambda v: v or "", inputs=peer_dropdown, outputs=peer_id)

        chat_out = gr.Chatbot(label="Messages", height=340)

        with gr.Row():
            msg_input = gr.Textbox(label="Message", placeholder="Type a message…", scale=7)
            send_btn = gr.Button("Send", scale=1, variant="primary")

        status_out = gr.Markdown(visible=False)

        async def refresh_peers():
            peers = _get_known_peers(bus)
            return gr.update(choices=peers, value=peers[0] if peers else None)

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

            recipient = peer.strip() if peer else getattr(bus, "node_id_full", "")
            if recipient == "*":
                all_peers = _get_known_peers(bus)
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
                    history.append({"role": "assistant", "content": f"[echo] {msg}"})
                elif status == "delivered":
                    history.append({"role": "assistant", "content": f"✓ delivered to {recipient[:24]}"})
                note = f"✓ {status} → `{recipient[:32]}`"
                return history, "", gr.update(visible=True, value=note)
            except Exception as e:
                history = [
                    *history,
                    {"role": "user", "content": msg},
                    {"role": "assistant", "content": f"Error: {e}"},
                ]
                return history, "", gr.update(visible=False)

        refresh_peers_btn.click(refresh_peers, outputs=peer_dropdown)
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
