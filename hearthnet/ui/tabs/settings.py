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
        with gr.Accordion("📱 Join This Mesh — Connecting Nodes & Meshes", open=False):
            gr.Markdown(f"""
### How to connect nodes and meshes

HearthNet uses **three complementary discovery methods**. Use whichever fits your situation.

---

#### Option A — Same LAN / Wi-Fi (zero-config, automatic)

Any two devices on the same network find each other automatically via **mDNS + UDP broadcast**.

```bash
# Device 1 (already running — this node)
python -m hearthnet.cli run

# Device 2 (new node — same Wi-Fi/LAN)
python -m hearthnet.cli run
# ↳ peers discover each other within ~5 seconds, no config needed
```

Check discovery: **Settings → Refresh Peers** or:
```bash
python -m hearthnet.cli peers
```

---

#### Option B — Invite QR (different networks, phones, remote nodes)

Generate an invite link below and share it with the other node:

```bash
# On the invitee device:
python -m hearthnet.cli invite redeem "hnvite://v1/..."
# ↳ adds this node as a peer and connects immediately

# Or paste into the CLI interactively:
python -m hearthnet.cli invite redeem
```

The QR encodes your **public endpoint + community identity + trust level**.
The invitee does NOT need to be on the same LAN.

**To connect to the HF Space demo from your local node:**
```bash
python -m hearthnet.cli invite redeem \\
  "hnvite://v1/hf-space-1c95381d?host=build-small-hackathon-hearthnet.hf.space&port=443&transport=https&level=member"
```
Then check: `python -m hearthnet.cli peers` — the Space node should appear.

---

#### Option C — Relay server (cross-internet, firewalls)

For nodes behind NAT/firewalls that can't accept inbound connections:

```toml
# ~/.hearthnet/config.toml
[transport]
relay_url = "wss://your-relay.example.com"
```

The relay forwards messages between nodes — no direct connection needed.
HearthNet M15 defines the relay tier protocol.

---

#### Connecting THREE meshes (or more)

Each mesh is a **community** — a shared identity. To bridge three communities:

```python
# Node that spans two meshes — registered in both:
node = HearthNode("bridge-node", "Bridge", community_id="ed25519:community-A")
node.join_community("ed25519:community-B", invite_link="hnvite://...")

# Cross-mesh capability call:
await node.bus.call("rag.query", (1,0),
    {{"params": {{"corpus": "community-B-corpus"}}, "input": {{"query": "..."}}}}
)
```

Or more simply: run two separate nodes on the same machine, each in a different community,
and connect them via LAN (Option A). They will see each other's capabilities across communities.
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
                    import os
                    from pathlib import Path

                    from hearthnet.identity.keys import load_or_generate
                    from hearthnet.ui.onboarding import encode_invite, make_invite

                    kp = load_or_generate(Path.home() / ".hearthnet" / "keys")
                    # Detect whether we're on HF Space or local
                    hf_space_host = os.getenv("SPACE_HOST")  # e.g. build-small-hackathon-hearthnet.hf.space
                    if hf_space_host:
                        public_host = hf_space_host
                        public_port = 443
                        transport = "https"
                    else:
                        port_obj = getattr(config, "transport", None)
                        public_port = getattr(port_obj, "port", 7080) if port_obj else 7080
                        public_host = "127.0.0.1"
                        transport = "http"

                    cm_prov = getattr(bus, "community_manifest_provider", None)
                    cm = cm_prov() if cm_prov else None
                    if cm is None:
                        link = (
                            f"hnvite://v1/{bus.node_id_full}"
                            f"?host={public_host}&port={public_port}&transport={transport}&level={level}"
                        )
                        qr_data = link
                    else:
                        from hearthnet.identity.manifest import Endpoint

                        blob = make_invite(
                            invitee_node_id_full=invitee or "ed25519:any",
                            inviter_kp=kp,
                            community_manifest=cm,
                            bootstrap_endpoints=[
                                Endpoint(transport=transport, host=public_host, port=public_port)
                            ],
                            initial_level=level,
                        )
                        link = encode_invite(blob)
                        qr_data = link

                    note = ""
                    if hf_space_host:
                        note = f"\n\n> ℹ️ This invite uses the **HF Space URL** (`{public_host}`). Peers outside the Space can use it."
                    else:
                        note = f"\n\n> ℹ️ Host is `{public_host}:{public_port}`. Make sure this is reachable by the invitee."
                    return _qr_svg(qr_data), link + note
                except Exception as exc:
                    return f"<p style='color:#f44'>Error: {exc}</p>", f"Error: {exc}"

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
                    backends_info = [
                        f"`{b.name}` \u2192 `{b.url or 'local'}`"
                        for b in getattr(l_cfg, "backends", [])
                    ]
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
| M01 Identity | docs/M01-identity.md | ✅ Ed25519 keys, manifests, community policy |
| M02 Discovery | docs/M02-discovery.md | ✅ mDNS + UDP multicast |
| M03 Bus | docs/M03-bus.md | ✅ capability routing, health, trust levels |
| M04 LLM | docs/M04-llm.md | ✅ Ollama / llama.cpp / LM Studio / HF / Anthropic |
| M05 RAG | docs/M05-rag.md | ✅ ChromaDB + SentenceTransformers + reranker |
| M06 Marketplace | docs/M06-marketplace.md | ✅ event-sourced, post/list/search/expire |
| M07 Blobs | docs/M07-file-blobs.md | ✅ BLAKE3 CID store, upload/download/list |
| M08 UI | docs/M08-ui.md | ✅ 8 tabs + themes + topology component |
| M09 Emergency | docs/M09-emergency.md | ✅ async probe loop, anti-flap |
| M10 Chat | docs/M10-chat.md | ✅ event-sourced, Lamport clocks |
| M11 Embedding | docs/M11-embedding.md | ✅ SentenceTransformers + SimpleHash fallback |
| M12 CLI | docs/M12-cli.md | ✅ run / call / log / rag / invite / version / erase |
| M13 Onboarding | docs/M13-onboarding.md | ✅ invite link + QR + redeem |
| M14 Federation | docs/p2_p3/M14-federation.md | ✅ bilateral peering, signed bridges |
| M15 Relay | docs/p2_p3/M15-relay-tier.md | ✅ NAT traversal relay tier |
| M16 Tokens | docs/p2_p3/M16-tokens.md | ✅ scoped capability tokens (hntoken://) |
| M17 OCR | docs/p2_p3/M17-ocr.md | ✅ Tesseract / TrOCR |
| M18 Translation | docs/p2_p3/M18-translation.md | ✅ NLLB-200 |
| M19 STT/TTS | docs/p2_p3/M19-stt-tts.md | ✅ Whisper STT / EdgeTTS synthesis |
| M20 Vision | docs/p2_p3/M20-vision.md | ✅ Florence-2 image captioning/VQA |
| M21 Tool Calls | docs/p2_p3/M21-tool-calls.md | ✅ ToolExecutor + plant identification |
| M22 Mobile | docs/p2_p3/M22-mobile-native.md | ✅ PWA manifest + service worker |
| M23 E2E Encrypt | docs/p2_p3/M23-e2e-encryption.md | ✅ X3DH + Double Ratchet |
| M24 Rerank | docs/p2_p3/M24-rerank.md | ✅ BGE / CrossEncoder |
| M25 Group Chat | docs/p2_p3/M25-group-chat.md | ✅ event-sourced thread rooms |
| M26 Distrib. Inference | docs/p2_p3/M26-distributed-inference.md | 🔬 shard advertise + pipeline plan (no torch sharding yet) |
| M27 MoE Routing | docs/p2_p3/M27-moe-routing.md | 🔬 expert register/route/score |
| M28 FedLearn | docs/p2_p3/M28-fedlearn.md | 🔬 coordinator + round manifest |
| M29 LoRa Beacons | docs/p2_p3/M29-lora-beacons.md | 🔬 frame encoding (hardware needed) |
| M30 Evidence | docs/p2_p3/M30-evidence-ebkh.md | 🔬 claim graph + EBKH bridge |
| M31 Civil Defense | docs/p2_p3/M31-civil-defense.md | 🔬 alert pipeline + role certs |
| M32 Protocol | docs/p2_p3/M32-protocol-standard.md | ✅ version list + conformance report |
| X01 Transport | docs/X01-transport.md | ✅ FastAPI server + SSE + backpressure |
| X02 Events | docs/X02-events.md | ✅ SQLite WAL + Lamport + gossip sync |
| X03 Observability | docs/X03-observability.md | ✅ tracing + metrics + TrackioExporter |
| X04 Config | docs/X04-config.md | ✅ typed TOML config + ResearchConfig flags |
| X05 DHT | docs/p2_p3/X05-dht.md | ✅ Kademlia routing table |
| X06 WebSocket | docs/p2_p3/X06-websocket.md | ✅ pubsub + StateBus |
| X07 Federated Metrics | docs/p2_p3/X07-federated-metrics.md | ✅ OTLP export |
| X08 Tensor Transport | docs/p2_p3/X08-tensor-transport.md | 🔬 chunked tensor stream stub |
| X09 Conformance Suite | docs/p2_p3/X09-conformance-suite.md | ✅ 21-check runner |
| Model Distribution | BitTorrent-style weight transfer | ✅ BLAKE3 CID chunk pull |

> 🔬 = experimental, feature-flag gated (`config.research.*`). All other modules are stable.
""")
