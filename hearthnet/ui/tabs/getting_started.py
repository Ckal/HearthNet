"""Getting Started tab — node setup, deployment options, distribution guide."""

from __future__ import annotations


def build_getting_started_tab():
    import gradio as gr

    with gr.Column():
        gr.Markdown("""### Getting Started with HearthNet

HearthNet is a **local-first community AI mesh**. Each participant runs a node
on their own hardware. Nodes discover each other automatically and share AI
capabilities, files, and community posts — no central server required.

---

## Quick Start (any device with Python)

```bash
# 1. Install from source (pip install hearthnet coming once published to PyPI)
git clone https://huggingface.co/spaces/build-small-hackathon/HearthNet
cd HearthNet
pip install -e .

# 2. Run a node
python -m hearthnet.cli run

# 3. Open the UI
# http://localhost:7860
```

Other devices on the **same Wi-Fi/LAN discover this node automatically** (mDNS).
No configuration needed for same-network peers.

> **PyPI package**: `pip install hearthnet` will work once the package is published.
> Until then use `pip install -e .` from the cloned repo.

---

## What Works Where

| Feature | HF Space | Local Node |
|---------|----------|------------|
| Ask / LLM chat | SmolLM2-135M | Ollama / llama.cpp / any HF model |
| RAG (knowledge base) | pre-seeded corpus | upload your own docs |
| Direct messaging (Chat) | single-node only | real delivery to peers |
| Mesh topology graph | no peers on Space | live SVG with all discovered peers |
| Marketplace posts | single-node | replicated across mesh |
| File sharing (blobs) | local only | content-addressed peer transfer |
| Emergency mode | 30s probe | 30s probe |
| MoE expert routing | disabled | routes queries to best node |
| BitTorrent model weights | disabled | pull GGUF / safetensors from peer |
| Plant identification | unavailable | Florence-2 vision + LLM parse |

---

## Setting Up a Second Node

**Option A — Same LAN (automatic)**
```bash
# On any other device on the same Wi-Fi:
git clone https://huggingface.co/spaces/build-small-hackathon/HearthNet
cd HearthNet && pip install -e .
python -m hearthnet.cli run
# Both nodes see each other within ~5 seconds (mDNS + UDP broadcast)
```

**Option B — Different network (invite link)**
1. Open Settings → Join This Mesh → Generate Invite QR
2. Share the link or scan QR on the new device
3. `python -m hearthnet.cli invite redeem <link>`

**Option C — Raspberry Pi**
```bash
# Raspbian / any ARM Linux:
git clone https://huggingface.co/spaces/build-small-hackathon/HearthNet
cd HearthNet && pip install -e .
python -m hearthnet.cli run --host 0.0.0.0 --port 7860
# Access from phone/laptop: http://raspberry-pi-ip:7860
```

---

## MoE Expert Routing (Phase 3 — M27)

Each node in the mesh can advertise itself as an **expert** in certain topics.
When a query arrives, `moe.route` scores all known experts and returns the best match.

```python
import asyncio
from hearthnet.node import HearthNode

node = HearthNode("medical-pi", "Medical Node", "ed25519:community")
node.install_services(corpus="medical")

# Advertise this node as a medical expert
asyncio.run(node.bus.call("moe.register", (1, 0), {
    "input": {
        "expert_id": f"model:{node.node_id}",
        "expert_type": "model",
        "topic_tags": ["first_aid", "medication", "triage", "medical"],
        "confidence_score": 0.85,
        "community_id": "ed25519:community",
        "name": "Medical Node",
        "ttl_seconds": 3600,
    }
}))

# Another node routes a query to the best expert:
result = asyncio.run(node.bus.call("moe.route", (1, 0), {
    "input": {"query": "what is the dosage for ibuprofen?", "top_k": 3}
}))
# {"output": {"candidates": [{"expert_id": "model:medical-pi", "score": 0.92, ...}]}}
```

**Expert types**: `model` (LLM node), `service` (OCR/translation node),
`human` (on-call person), `external` (public API opt-in).

---

## BitTorrent-Style Model Sharing (Phase 3 — M26)

Nodes advertise which model weight files they hold. Peers can pull models
chunk-by-chunk using content-addressed transfer (BLAKE3 CID).
This is analogous to BitTorrent but peer-to-peer over the HearthNet transport.

```python
# On Node A (has llama3.2-3b-q4.gguf):
# ModelDistributionService auto-scans ~/.ollama/models and your models_dir
# It registers as model.advertise, model.list, model.chunk_read automatically

# On Node B (wants the model):
result = await node.bus.call("model.pull", (1, 0), {
    "input": {
        "model_name": "llama3.2:3b",
        "source_node": "node-a-id",       # node_id of the provider
        "dest_dir": "~/.hearthnet/models", # optional; defaults to ~/.hearthnet/models
    }
})
job_id = result["output"]["job_id"]

# Poll progress:
status = await node.bus.call("model.status", (1, 0), {
    "input": {"job_id": job_id}
})
# {"output": {"progress": 0.42, "received_chunks": 84, "total_chunks": 200, ...}}
```

Files are saved to `~/.hearthnet/blobs/` (BLAKE3 CID-addressed) and
optionally installed into Ollama if available.

**CLI shortcut:**
```bash
python -m hearthnet.cli call model.list 1 0 '{}'
python -m hearthnet.cli call model.pull 1 0 '{"model_name":"llama3.2:3b","source_node":"node-a"}'
```

---

## Plant Identification Tool (M21 tool calls)

The `tool.plant_identify` capability identifies plants from images.

```python
import base64

# Load any JPEG/PNG image
with open("plant.jpg", "rb") as f:
    img_b64 = base64.b64encode(f.read()).decode()

result = await node.bus.call("tool.plant_identify", (1, 0), {
    "input": {
        "image_b64": img_b64,
        "hints": ["northern Europe", "found near water", "July"],
    }
})
# {
#   "name": "Urtica dioica",
#   "common_name": "Stinging Nettle",
#   "confidence": 0.81,
#   "family": "Urticaceae",
#   "is_toxic": false,
#   "edible_parts": ["young leaves (cooked)"],
#   "care_tips": ["wear gloves when handling", "boiling removes sting"],
#   "backend_used": "local_vision"
# }
```

**Backend priority:**
1. **Local vision** — Florence-2 via `vision.describe` + LLM parse (no internet)
2. **HF Inference API** — set `HEARTHNET_HF_TOKEN` to enable (requires internet)
3. **Unavailable** — structured error with setup instructions

**With LLM tool calls (M21):**
```python
from hearthnet.services.llm.tools import ToolExecutor
from hearthnet.services.tools.plant import PLANT_TOOL_DEFINITION

executor = ToolExecutor(bus=node.bus, tools=[PLANT_TOOL_DEFINITION])
# Pass executor to LlmService — the LLM can now call plant_identify mid-generation
```

---

## Adding a Specialized Node

Each node only needs to register the capabilities it has hardware for:

```python
from hearthnet.node import HearthNode
from hearthnet.services.ocr import OcrService     # Tesseract / TrOCR

node = HearthNode("ocr-pi", "Scanner Pi", "ed25519:community")
node.install_services()
node.bus.register_service(OcrService())
node.start()
# Now ANY node in the mesh can call bus.call("ocr.extract", ...)
# and this Pi answers it automatically
```

Other specialized node patterns:
- **Medical RAG node**: `RagService(corpus="medical")` + large medical embedding model
- **Translation node**: `TranslationService()` with NLLB-200 for low-resource languages
- **LoRa beacon node**: `LoraBeaconService(serial_port="/dev/ttyUSB0")` for 868 MHz offline heartbeats
- **Thin client**: No services installed — only routes requests to other nodes

---

## Distribution Options

| Method | Best for |
|--------|----------|
| `pip install -e .` | Development, Raspberry Pi, servers |
| `pip install hearthnet` | Once published to PyPI (coming soon) |
| **Browser (PWA)** | Any device — open `http://node-ip:7860`. Add to home screen. |
| **Docker** | Servers: `docker build -t hearthnet . && docker run -p 7860:7860 hearthnet` |
| **Android app** | Browser to a local node; native app planned (M22) |
| **Relay node** | One node with public IP acts as relay (M15); remote nodes connect through it |

---

## Testing Your Setup

```bash
# All unit tests (102 tests, 0 failures):
pytest tests/ -q

# Skip E2E (Playwright) tests:
pytest tests/ -q --ignore=tests/test_e2e_user_stories.py

# Two-node local demo:
python -m scripts.demo_two_nodes

# Test MoE routing:
python -c "
from hearthnet.node import HearthNode
import asyncio

node = HearthNode('test', 'Test', 'ed25519:demo')
node.install_demo_services()

async def main():
    # Register a demo expert
    await node.bus.call('moe.register', (1, 0), {'input': {
        'expert_id': 'model:test', 'expert_type': 'model',
        'topic_tags': ['first_aid','emergency'], 'confidence_score': 0.9,
        'community_id': 'ed25519:demo'
    }})
    result = await node.bus.call('moe.route', (1, 0), {'input': {'query': 'emergency first aid'}})
    print(result['output'])

asyncio.run(main())
"
```
""")
