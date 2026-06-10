"""Settings + Node Management tab.

Spec: docs/M08-ui.md §5.2, docs/M13-onboarding.md, docs/M01-identity.md
Impl-ref: §15 (UiApp), §16 (onboarding), §17 (CLI/node.py)

Shows:
- This node's identity (node_id, profile, community)
- All known peers with their capabilities
- Invite QR code generation
- RAG corpus ingest
- Config overview (transport port, discovery, backends)
"""
from __future__ import annotations


def build_settings_tab(config=None, meta: dict | None = None, bus=None):
    import gradio as gr

    meta = meta or {}

    with gr.Column():
        gr.Markdown("### ⚙️ Node & Settings")

        # --- Node Identity ------------------------------------------------
        with gr.Accordion("🪪 Node Identity", open=True):
            node_id_val = meta.get("node_id", "not initialized")
            community_val = meta.get("community_id", "none")
            profile_val = meta.get("profile", "hearth")

            gr.Markdown(f"""
| Field | Value |
|-------|-------|
| Node ID | `{node_id_val}` |
| Profile | `{profile_val}` |
| Community | `{community_val[:40]}` |
""")

        # --- Live peer list -----------------------------------------------
        with gr.Accordion("🌐 Connected Peers & Capabilities", open=True):
            peers_out = gr.JSON(label="Peers", value=[])
            refresh_peers_btn = gr.Button("🔄 Refresh Peers", size="sm")

            async def get_peers():
                if bus is None:
                    return [{"node_id": "demo-node", "profile": "hearth", "capabilities": ["llm.chat"]}]
                try:
                    snap = bus.topology_snapshot()
                    result = []
                    for p in snap.peers:
                        result.append({
                            "node_id": p.node_id,
                            "display_name": p.display_name,
                            "profile": p.profile,
                            "source": p.source,
                            "last_seen_s_ago": round(__import__('time').time() - p.last_seen, 1),
                        })
                    caps = []
                    for e in snap.capabilities_remote:
                        caps.append({
                            "node_id": e.node_id[:20],
                            "capability": f"{e.descriptor.name}@{e.descriptor.version[0]}.{e.descriptor.version[1]}",
                            "health": f"{e.success_rate:.0%}",
                        })
                    return {"peers": result, "remote_capabilities": caps}
                except Exception as exc:
                    return {"error": str(exc)}

            refresh_peers_btn.click(get_peers, outputs=peers_out)

        # --- Invite / Onboarding ------------------------------------------
        with gr.Accordion("📨 Invite a Node", open=False):
            gr.Markdown("""
Generate an invite link for another device or Raspberry Pi.

The other node can join by running:  
```
python -m hearthnet.cli invite redeem <paste-link-here>
```
Or by scanning the QR code in the HearthNet app (M22).
""")
            with gr.Row():
                invitee_id = gr.Textbox(label="Invitee Node ID (optional)", placeholder="ed25519:...", scale=3)
                invite_level = gr.Dropdown(label="Trust Level", choices=["member", "trusted"], value="member", scale=1)
            make_invite_btn = gr.Button("Generate Invite Link", variant="primary")
            invite_out = gr.Textbox(label="Invite Link", lines=2)

            async def gen_invite(invitee, level):
                if bus is None:
                    return "hnvite://v1/demo-invite-not-real"
                try:
                    from hearthnet.ui.onboarding import make_invite, encode_invite
                    from hearthnet.identity.keys import load_or_generate
                    from pathlib import Path
                    kp = load_or_generate(Path.home() / ".hearthnet" / "keys")
                    cm_prov = getattr(bus, "community_manifest_provider", None)
                    cm = cm_prov() if cm_prov else None
                    if cm is None:
                        return "Error: community manifest not available"
                    from hearthnet.identity.manifest import Endpoint
                    blob = make_invite(
                        invitee_node_id_full=invitee or "ed25519:any",
                        inviter_kp=kp,
                        community_manifest=cm,
                        bootstrap_endpoints=[Endpoint(transport="http", host="127.0.0.1", port=7080)],
                        initial_level=level,
                    )
                    return encode_invite(blob)
                except Exception as exc:
                    return f"Error: {exc}"

            make_invite_btn.click(gen_invite, inputs=[invitee_id, invite_level], outputs=invite_out)

        # --- RAG Corpus Ingest -------------------------------------------
        with gr.Accordion("📚 RAG — Ingest Documents", open=False):
            gr.Markdown("""
Upload documents into the local knowledge base.  
Supported: `.txt`, `.md`, `.pdf` (PDF requires `pypdf`).  
Documents are chunked, embedded, and stored in ChromaDB.
""")
            with gr.Row():
                rag_corpus = gr.Textbox(label="Corpus name", value="community", scale=2)
                rag_file = gr.File(label="Document", scale=3)
            ingest_btn = gr.Button("Ingest", variant="primary")
            ingest_out = gr.JSON(label="Ingest result", visible=False)

            async def do_ingest(corpus, file_obj):
                if file_obj is None:
                    return gr.update(visible=True, value={"error": "No file selected"})
                if bus is None:
                    return gr.update(visible=True, value={"error": "Bus not connected"})
                try:
                    import base64
                    path = getattr(file_obj, "name", str(file_obj))
                    with open(path, "rb") as fh:
                        data = fh.read()
                    filename = path.split("/")[-1].split("\\")[-1]
                    r = await bus.call(
                        "rag.ingest",
                        (1, 0),
                        {"input": {
                            "corpus": corpus or "community",
                            "doc_title": filename,
                            "text": data.decode("utf-8", errors="replace"),
                        }},
                    )
                    return gr.update(visible=True, value=r.get("output", r))
                except Exception as exc:
                    return gr.update(visible=True, value={"error": str(exc)})

            ingest_btn.click(do_ingest, inputs=[rag_corpus, rag_file], outputs=ingest_out)

        # --- Config overview ---------------------------------------------
        with gr.Accordion("📋 Configuration Overview", open=False):
            if config is not None:
                t = getattr(config, "transport", None)
                d = getattr(config, "discovery", None)
                l_cfg = getattr(config, "llm", None)
                backends_info = []
                if l_cfg:
                    for b in getattr(l_cfg, "backends", []):
                        backends_info.append(f"`{b.name}` → `{b.url or 'local'}`")
                gr.Markdown(f"""
| Setting | Value |
|---------|-------|
| Transport host:port | `{getattr(t,'host','?')}:{getattr(t,'port','?')}` |
| mDNS discovery | `{getattr(d,'mdns_enabled','?')}` |
| UDP discovery | `{getattr(d,'udp_enabled','?')}` |
| LLM backends | {', '.join(backends_info) or 'none configured'} |
""")
            else:
                gr.Markdown("*Config not available — run via `python app.py` or `python -m hearthnet.cli run`*")

            gr.Markdown("""
#### Config file location
```
~/.hearthnet/config.toml
```
See `docs/HOWTO.md` for the full reference.
""")

        # --- Phase status -----------------------------------------------
        with gr.Accordion("🔬 Implementation Status", open=False):
            gr.Markdown("""
| Module | Spec | Status |
|--------|------|--------|
| M01 Identity | [docs/M01-identity.md](docs/M01-identity.md) | ✅ |
| M02 Discovery | [docs/M02-discovery.md](docs/M02-discovery.md) | ✅ mDNS/UDP |
| M03 Bus | [docs/M03-bus.md](docs/M03-bus.md) | ✅ |
| M04 LLM | [docs/M04-llm.md](docs/M04-llm.md) | ✅ Ollama/llama.cpp/HF/Nemotron/MiniCPM |
| M05 RAG | [docs/M05-rag.md](docs/M05-rag.md) | ✅ Chroma |
| M06 Marketplace | [docs/M06-marketplace.md](docs/M06-marketplace.md) | ✅ event-sourced |
| M07 Blobs | [docs/M07-file-blobs.md](docs/M07-file-blobs.md) | ✅ BLAKE3 |
| M08 UI | [docs/M08-ui.md](docs/M08-ui.md) | ✅ 6 tabs |
| M09 Emergency | [docs/M09-emergency.md](docs/M09-emergency.md) | ✅ async probe |
| M10 Chat | [docs/M10-chat.md](docs/M10-chat.md) | ✅ event-sourced |
| M11 Embedding | [docs/M11-embedding.md](docs/M11-embedding.md) | ✅ |
| M12 CLI | [docs/M12-cli.md](docs/M12-cli.md) | ✅ |
| M13 Onboarding | [docs/M13-onboarding.md](docs/M13-onboarding.md) | ✅ QR/invite |
| M14 Federation | [docs/p2_p3/M14-federation.md](docs/p2_p3/M14-federation.md) | ✅ |
| M15 Relay | [docs/p2_p3/M15-relay-tier.md](docs/p2_p3/M15-relay-tier.md) | ✅ |
| M16 Tokens | [docs/p2_p3/M16-tokens.md](docs/p2_p3/M16-tokens.md) | ✅ |
| M17 OCR | [docs/p2_p3/M17-ocr.md](docs/p2_p3/M17-ocr.md) | ✅ Tesseract/TrOCR |
| M18 Translation | [docs/p2_p3/M18-translation.md](docs/p2_p3/M18-translation.md) | ✅ NLLB |
| M19 STT/TTS | [docs/p2_p3/M19-stt-tts.md](docs/p2_p3/M19-stt-tts.md) | ✅ Whisper/EdgeTTS |
| M20 Vision | [docs/p2_p3/M20-vision.md](docs/p2_p3/M20-vision.md) | ✅ Florence-2 |
| M21 Tool Calls | [docs/p2_p3/M21-tool-calls.md](docs/p2_p3/M21-tool-calls.md) | ✅ |
| M22 Mobile | [docs/p2_p3/M22-mobile-native.md](docs/p2_p3/M22-mobile-native.md) | ✅ anchor-side |
| M23 E2E Encrypt | [docs/p2_p3/M23-e2e-encryption.md](docs/p2_p3/M23-e2e-encryption.md) | ✅ X3DH+Ratchet |
| M24 Rerank | [docs/p2_p3/M24-rerank.md](docs/p2_p3/M24-rerank.md) | ✅ BGE/CrossEncoder |
| M25 Group Chat | [docs/p2_p3/M25-group-chat.md](docs/p2_p3/M25-group-chat.md) | ✅ |
| M26-M31 | Phase 3 | 🔬 experimental |
| X01 Transport | [docs/X01-transport.md](docs/X01-transport.md) | ✅ FastAPI |
| X02 Events | [docs/X02-events.md](docs/X02-events.md) | ✅ SQLite |
| X03 Observability | [docs/X03-observability.md](docs/X03-observability.md) | ✅ |
| X04 Config | [docs/X04-config.md](docs/X04-config.md) | ✅ |
| X05 DHT | [docs/p2_p3/X05-dht.md](docs/p2_p3/X05-dht.md) | ✅ Kademlia |
| X06 WebSocket | [docs/p2_p3/X06-websocket.md](docs/p2_p3/X06-websocket.md) | ✅ |
| X07 Federated Metrics | [docs/p2_p3/X07-federated-metrics.md](docs/p2_p3/X07-federated-metrics.md) | ✅ |
""")
