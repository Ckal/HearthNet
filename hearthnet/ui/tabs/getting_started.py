"""Getting Started tab — node setup, deployment options, distribution guide."""

from __future__ import annotations


def build_getting_started_tab():
    import gradio as gr

    with gr.Column():
        gr.Markdown("""### 🚀 Getting Started with HearthNet

HearthNet is a **local-first community AI mesh**. Each participant runs a node
on their own hardware. Nodes discover each other automatically and share AI
capabilities, files, and community posts — no central server required.

---

## Quick Start (any device with Python)

```bash
# 1. Install
pip install hearthnet
# or from source:
git clone https://huggingface.co/spaces/build-small-hackathon/HearthNet
cd HearthNet && pip install -e .

# 2. Run
python -m hearthnet.cli run

# 3. Open the UI
# http://localhost:7860
```

Other devices on the **same Wi-Fi/LAN discover this node automatically** (mDNS).
No configuration needed for same-network peers.

---

## What Works Where

| Feature | HF Space | Local Node |
|---------|----------|------------|
| Ask / LLM chat | ✅ SmolLM2-135M | ✅ Ollama / llama.cpp / any HF model |
| RAG (knowledge base) | ✅ pre-seeded corpus | ✅ upload your own docs |
| Direct messaging (Chat) | ⚠️ single-node only | ✅ real delivery to peers |
| Mesh topology graph | ⚠️ no peers on Space | ✅ live SVG with all discovered peers |
| Marketplace posts | ✅ single-node | ✅ replicated across mesh |
| File sharing (blobs) | ✅ local only | ✅ content-addressed peer transfer |
| Emergency mode | ✅ | ✅ automatic 30s probe |
| Multi-node routing | ❌ | ✅ OCR node, medical RAG node, etc. |
| BitTorrent model weights | ❌ | ✅ pull GGUF from peer |

---

## Setting Up a Second Node

**Option A — Same LAN (automatic)**
```bash
# On any other device on the same Wi-Fi:
pip install hearthnet
python -m hearthnet.cli run
# Both nodes see each other within ~5 seconds
```

**Option B — Different network (invite link)**
1. Open Settings → Join This Mesh → Generate Invite QR
2. Share the link or scan QR on the new device
3. `python -m hearthnet.cli invite redeem <link>`

**Option C — Raspberry Pi**
```bash
# Raspbian / any ARM Linux:
pip3 install hearthnet
python3 -m hearthnet.cli run --host 0.0.0.0 --port 7860
# Access from phone/laptop: http://raspberry-pi-ip:7860
```

---

## Adding a Specialized Node

Each node only needs to register the capabilities it has hardware for:

```python
from hearthnet.node import HearthNode
from hearthnet.services.ocr import OcrService     # Tesseract / TrOCR

node = HearthNode("ocr-pi", "Scanner Pi", "ed25519:...")
node.bus.register_service(OcrService())
node.start()
# Now ANY node in the mesh can call bus.call("ocr.extract", ...)
# and this Pi answers it automatically
```

See **Settings → Specialized Nodes** for more examples (medical RAG, translation, thin client).

---

## Distribution Options

| Method | Best for |
|--------|----------|
| `pip install hearthnet` | Developers, servers, Raspberry Pi |
| **Browser (PWA)** | Any device — open `http://node-ip:7860` in any browser. Gradio serves a PWA-compatible interface. Add to home screen on Android/iOS. |
| **Docker** | Servers, always-on nodes: `docker run -p 7860:7860 hearthnet/node` |
| **Android app** | Access via browser to a local node. Full native app planned (M22). |
| **Relay node** | One node with a public IP acts as relay (M15). Remote nodes connect through it. |

---

## Testing Your Setup

```bash
# Unit tests (no hardware required):
pytest tests/ -q --ignore=tests/test_e2e_playwright.py

# Full E2E user-story tests (requires playwright install chromium):
pytest tests/test_e2e_user_stories.py -v

# Two-node demo:
python -m scripts.demo_two_nodes

# Generate proof screenshots:
python -m scripts.gen_screenshots
# → docs/screenshots/stories/*.png
```
""")
