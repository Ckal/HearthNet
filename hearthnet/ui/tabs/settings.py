"""Settings + Node Management tab.

Spec: docs/M08-ui.md §5.2, docs/M13-onboarding.md, docs/M01-identity.md
Impl-ref: §15 (UiApp), §16 (onboarding), §17 (CLI/node.py)

Shows:
- This node's identity (node_id, profile, community)
- All known peers with their capabilities (live from bus registry)
- Join-mesh QR code + invite link generation
- How to add specialized nodes
- RAG corpus ingest
- Config overview (transport port, discovery, backends)
"""

from __future__ import annotations


def _qr_svg(data: str) -> str:
    """Generate a QR code SVG using the qrcode library if available."""
    try:
        import io

        import qrcode  # type: ignore[import]
        import qrcode.image.svg  # type: ignore[import]

        factory = qrcode.image.svg.SvgPathImage
        img = qrcode.make(data, image_factory=factory, box_size=6, border=2)
        buf = io.BytesIO()
        img.save(buf)
        svg_str = buf.getvalue().decode("utf-8")
        return (
            f'<div style="background:white;display:inline-block;padding:8px;'
            f'border-radius:4px">{svg_str}</div>'
        )
    except Exception:
        return (
            f'<pre style="background:#1a2a28;color:#4CAF50;padding:12px;border-radius:4px;'
            f'word-break:break-all;font-size:11px">{data}</pre>'
            '<p style="color:#888;font-size:11px">'
            "Install <code>qrcode[svg]</code> for a scannable QR image.</p>"
        )


def build_settings_tab(config=None, meta: dict | None = None, bus=None):
    import gradio as gr

    meta = meta or {}

    # Enrich meta from live bus when available
    if bus is not None:
        meta.setdefault("node_id", getattr(bus, "node_id_full", "unknown"))
        meta.setdefault("community_id", getattr(bus, "community_id", "unknown"))

    node_id_val = meta.get("node_id", "not initialized")
    community_val = meta.get("community_id", "none")
    profile_val = meta.get("profile", "hearth")

    with gr.Column():
        gr.Markdown("""### ⚙️ Node Settings & Management

Inspect this node's identity, manage peers, ingest documents into the knowledge base,
invite new nodes to join the mesh, and review configuration.
""")

        # --- Node Identity ------------------------------------------------
        with gr.Accordion("🪪 Node Identity", open=True):
            gr.Markdown(f"""
Each HearthNet node has a unique **ed25519 key pair** as its identity (M01).
The Node ID is the public key fingerprint — it never changes unless you regenerate keys.

| Field | Value |
|-------|-------|
| Node ID | `{node_id_val}` |
| Profile | `{profile_val}` |
| Community | `{community_val[:60]}` |

**Key file:** `~/.hearthnet/keys/`
""")

        # --- Live peer list -----------------------------------------------
        with gr.Accordion("🌐 Connected Peers & Capabilities", open=True):
            gr.Markdown("""
All peers currently visible in the **capability bus registry** (M02, M03).
Peers are auto-discovered via mDNS/UDP. Each entry shows their capabilities.
See the **Mesh** tab for a visual graph.
""")
            peers_out = gr.JSON(label="Peers (live from bus registry)", value={})
            refresh_peers_btn = gr.Button("🔄 Refresh Peers", size="sm")

            async def get_peers():
                if bus is None:
                    return {"error": "Bus not connected — run as a real node to see live peers"}
                try:
                    remote_entries = list(bus.registry.all_remote())
                    peer_caps: dict[str, list[str]] = {}
                    for e in remote_entries:
                        nid = e.node_id
                        peer_caps.setdefault(nid, []).append(
                            f"{e.descriptor.name}@{e.descriptor.version[0]}.{e.descriptor.version[1]}"
                        )
                    result = [
                        {"node_id": nid, "capabilities": caps, "capability_count": len(caps)}
                        for nid, caps in peer_caps.items()
                    ]
                    local_caps = [
                        f"{e.descriptor.name}@{e.descriptor.version[0]}.{e.descriptor.version[1]}"
                        for e in bus.registry.all_local()
                    ]
                    return {
                        "this_node": bus.node_id_full,
                        "local_capabilities": local_caps,
                        "local_capability_count": len(local_caps),
                        "peers": result,
                        "peer_count": len(result),
                    }
                except Exception as exc:
                    return {"error": str(exc)}

            refresh_peers_btn.click(get_peers, outputs=peers_out)

        # --- Join the Mesh (QR + invite) ----------------------------------
        with gr.Accordion("📱 Join This Mesh — QR Code & Invite Link", open=False):
            gr.Markdown("""
### How to add a new node to this mesh

**Option A — Scan QR (phones, tablets, Raspberry Pi)**
1. Install HearthNet: `pip install hearthnet` (or `git clone + pip install -e .`)
2. Scan QR or paste the invite link
3. Run: `python -m hearthnet.cli invite redeem <link>`

**Option B — Same LAN (auto-discovery)**
1. Install and start HearthNet on any device on the same Wi-Fi/LAN
2. `python -m hearthnet.cli run`
3. Nodes find each other via mDNS within ~5 seconds — no config needed

**Option C — Remote relay (M15)**  
Set `relay_url` in `~/.hearthnet/config.toml` for cross-internet connections.
""")
            qr_html = gr.HTML(
                value="<p style='color:#888'>Click Generate to create a scannable join QR.</p>"
            )
            with gr.Row():
                invitee_id = gr.Textbox(
                    label="Invitee Node ID (optional — blank = open invite)",
                    placeholder="ed25519:...",
                    scale=3,
                )
                invite_level = gr.Dropdown(
                    label="Trust Level",
                    choices=["member", "trusted"],
                    value="member",
                    scale=1,
                )
            make_invite_btn = gr.Button("🔑 Generate Invite QR + Link", variant="primary")
            invite_out = gr.Textbox(label="Invite Link (share this)", lines=2)

            async def gen_invite(invitee: str, level: str):
                if bus is None:
                    return "<p style='color:#f44'>Bus not connected — run as a real node.</p>", ""
                try:
                    from pathlib import Path

                    from hearthnet.identity.keys import load_or_generate
                    from hearthnet.ui.onboarding import encode_invite, make_invite

                    kp = load_or_generate(Path.home() / ".hearthnet" / "keys")
                    cm_prov = getattr(bus, "community_manifest_provider", None)
                    cm = cm_prov() if cm_prov else None
                    if cm is None:
                        port_obj = getattr(config, "transport", None)
                        port_val = getattr(port_obj, "port", 7080) if port_obj else 7080
                        link = (
                            f"hnvite://v1/{bus.node_id_full}"
                            f"?host=127.0.0.1&port={port_val}&level={level}"
                        )
                        return _qr_svg(link), link
                    from hearthnet.identity.manifest import Endpoint

                    blob = make_invite(
                        invitee_node_id_full=invitee or "ed25519:any",
                        inviter_kp=kp,
                        community_manifest=cm,
                        bootstrap_endpoints=[
                            Endpoint(transport="http", host="127.0.0.1", port=7080)
                        ],
                        initial_level=level,
                    )
                    link = encode_invite(blob)
                    return _qr_svg(link), link
                except Exception as exc:
                    return f"<p style='color:#f44'>Error: {exc}</p>", ""

            make_invite_btn.click(
                gen_invite,
                inputs=[invitee_id, invite_level],
                outputs=[qr_html, invite_out],
            )

        # --- Specialized Nodes -------------------------------------------
        with gr.Accordion("🔧 Specialized Nodes — How to Add Them", open=False):
            gr.Markdown("""
### Adding a Specialized Node to the Mesh

HearthNet uses **capability-based routing** (M03). Any node that registers a service
automatically becomes a provider for that capability across the entire mesh.

#### Example 1 — OCR-only node (scanner Raspberry Pi)
```python
from hearthnet.node import HearthNode
from hearthnet.services.ocr import OcrService   # registers ocr.extract@1.0

node = HearthNode("ocr-pi", "scanner", "ed25519:...")
node.bus.register_service(OcrService())
node.start()   # mDNS broadcasts ocr.extract@1.0 to the mesh
```
Any other node calls `bus.call("ocr.extract", ...)` and it routes here automatically.

#### Example 2 — Medical RAG node (curated corpus)
```python
from hearthnet.services.rag import RagService
rag = RagService()
rag.ingest("medical", "first-aid.pdf", text=...)
node.bus.register_service(rag)   # rag.query@1.0 + rag.ingest@1.0
```
`bus.call("rag.query", params={"corpus": "medical"}, ...)` routes here because
only this node has the `medical` corpus.

#### Example 3 — Thin client (no local AI)
```python
node = HearthNode("phone", "thin-client", "ed25519:...")
# No services registered — ALL bus.call() route to peer providers
node.start()
```

#### Routing score formula
```
score = base − latency_penalty − load_penalty + (100 if local else 0)
```
Local capabilities always beat remote ones of equal quality.
If a node is quarantined, the bus automatically fails over.

See `docs/HOWTO.md §12` and `tests/test_specialized_nodes.py` for full examples.
""")

        # --- RAG Corpus Ingest -------------------------------------------
        with gr.Accordion("📚 RAG — Ingest Documents into Knowledge Base", open=False):
            gr.Markdown("""
Upload documents to make them searchable via Retrieval-Augmented Generation (M05).

How it works:
1. Document is chunked and embedded locally (SentenceTransformers)
2. Chunks are stored in ChromaDB under the corpus name you choose
3. In the **Ask** tab, select this corpus to inject relevant context before the LLM answers

**Formats:** `.txt`, `.md`, `.pdf` (requires `pypdf`)  
**Corpus names:** use descriptive names like `medical`, `community`, `emergency`, `laws`
""")
            with gr.Row():
                rag_corpus = gr.Textbox(label="Corpus name", value="community", scale=2)
                rag_file = gr.File(label="Document file", scale=3)
            ingest_btn = gr.Button("📥 Ingest", variant="primary")
            ingest_out = gr.JSON(label="Ingest result", visible=False)

            async def do_ingest(corpus, file_obj):
                if file_obj is None:
                    return gr.update(visible=True, value={"error": "No file selected"})
                if bus is None:
                    return gr.update(visible=True, value={"error": "Bus not connected"})
                try:
                    path = getattr(file_obj, "name", str(file_obj))
                    with open(path, "rb") as fh:
                        data = fh.read()
                    filename = path.split("/")[-1].split("\\")[-1]
                    r = await bus.call(
                        "rag.ingest",
                        (1, 0),
                        {
                            "input": {
                                "corpus": corpus or "community",
                                "doc_title": filename,
                                "text": data.decode("utf-8", errors="replace"),
                            }
                        },
                    )
                    return gr.update(visible=True, value=r.get("output", r))
                except Exception as exc:
                    return gr.update(visible=True, value={"error": str(exc)})

            ingest_btn.click(do_ingest, inputs=[rag_corpus, rag_file], outputs=ingest_out)

        # --- Config overview ---------------------------------------------
        with gr.Accordion("📋 Configuration Overview", open=False):
            gr.Markdown(
                "**Config file:** `~/.hearthnet/config.toml` — See `docs/HOWTO.md` for all options."
            )
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
| Transport host:port | `{getattr(t, "host", "?")}:{getattr(t, "port", "?")}` |
| mDNS discovery | `{getattr(d, "mdns_enabled", "?")}` |
| UDP discovery | `{getattr(d, "udp_enabled", "?")}` |
| LLM backends | {", ".join(backends_info) or "none configured"} |
""")
            else:
                gr.Markdown(
                    "*Config not shown — pass `config=` to UiApp or run via `python -m hearthnet.cli run`*"
                )

        # --- Phase status -----------------------------------------------
        with gr.Accordion("🔬 Implementation Status", open=False):
            gr.Markdown("""
| Module | Spec | Status |
|--------|------|--------|
| M01 Identity | docs/M01-identity.md | ✅ ed25519 keypair |
| M02 Discovery | docs/M02-discovery.md | ✅ mDNS + UDP |
| M03 Bus | docs/M03-bus.md | ✅ capability routing |
| M04 LLM | docs/M04-llm.md | ✅ Ollama / llama.cpp / HF Transformers |
| M05 RAG | docs/M05-rag.md | ✅ ChromaDB + SentenceTransformers |
| M06 Marketplace | docs/M06-marketplace.md | ✅ event-sourced posts |
| M07 Blobs | docs/M07-file-blobs.md | ✅ BLAKE3 content-addressed store |
| M08 UI | docs/M08-ui.md | ✅ 7 tabs |
| M09 Emergency | docs/M09-emergency.md | ✅ async mode probe |
| M10 Chat | docs/M10-chat.md | ✅ event-sourced, Lamport clocks |
| M11 Embedding | docs/M11-embedding.md | ✅ SentenceTransformers |
| M12 CLI | docs/M12-cli.md | ✅ run / invite / status |
| M13 Onboarding | docs/M13-onboarding.md | ✅ invite link + QR |
| M14 Federation | docs/p2_p3/M14-federation.md | ✅ |
| M15 Relay | docs/p2_p3/M15-relay-tier.md | ✅ |
| M16 Tokens | docs/p2_p3/M16-tokens.md | ✅ |
| M17 OCR | docs/p2_p3/M17-ocr.md | ✅ Tesseract / TrOCR |
| M18 Translation | docs/p2_p3/M18-translation.md | ✅ NLLB |
| M19 STT/TTS | docs/p2_p3/M19-stt-tts.md | ✅ Whisper / EdgeTTS |
| M20 Vision | docs/p2_p3/M20-vision.md | ✅ Florence-2 |
| M21 Tool Calls | docs/p2_p3/M21-tool-calls.md | ✅ |
| M22 Mobile | docs/p2_p3/M22-mobile-native.md | ✅ anchor-side |
| M23 E2E Encrypt | docs/p2_p3/M23-e2e-encryption.md | ✅ X3DH + Double Ratchet |
| M24 Rerank | docs/p2_p3/M24-rerank.md | ✅ BGE / CrossEncoder |
| M25 Group Chat | docs/p2_p3/M25-group-chat.md | ✅ |
| M26-M31 | Phase 3 | 🔬 experimental |
| X01 Transport | docs/X01-transport.md | ✅ FastAPI |
| X02 Events | docs/X02-events.md | ✅ SQLite |
| X03 Observability | docs/X03-observability.md | ✅ |
| X04 Config | docs/X04-config.md | ✅ TOML |
| X05 DHT | docs/p2_p3/X05-dht.md | ✅ Kademlia |
| X06 WebSocket | docs/p2_p3/X06-websocket.md | ✅ |
| X07 Federated Metrics | docs/p2_p3/X07-federated-metrics.md | ✅ |
| Model Distribution | docs/M07+M26 | ✅ BitTorrent-style weight transfer |
""")
