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
# 1. Clone the repo (PyPI package coming soon — use git clone for now)
git clone https://huggingface.co/spaces/build-small-hackathon/HearthNet
cd HearthNet
pip install -e .

# 2. Run your local node
python -m hearthnet.cli run

# 3. Open the UI
# http://localhost:7860
```

The **HF Space** above is the public demo — single node, SmolLM2-135M, no real peer mesh.
A **local install** gives you Ollama/llama.cpp models, real peer discovery, file sharing, and chat.

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

---

## Calling a Capability on Any Node

Every feature in HearthNet is a **named capability** on the bus. Calling one is always the same pattern:

```python
import asyncio
from hearthnet.node import HearthNode

node = HearthNode("my-node", "My Node", "ed25519:community")
node.install_demo_services()  # registers llm.chat, rag.query, chat.send, etc.

async def main():
    # --- LLM chat ---
    result = await node.bus.call("llm.chat", (1, 0), {
        "params": {},           # {} = let the bus pick the best node
        "input": {
            "messages": [
                {"role": "user", "content": "What is HearthNet?"}
            ]
        }
    })
    print(result["output"]["message"]["content"])

    # --- RAG query ---
    result = await node.bus.call("rag.query", (1, 0), {
        "params": {"corpus": "community"},   # route to node with this corpus
        "input": {"query": "emergency water purification", "k": 3}
    })
    for chunk in result["output"]["chunks"]:
        print(chunk["text"][:80])

    # --- Send a chat message ---
    result = await node.bus.call("chat.send", (1, 0), {
        "input": {"recipient": "bob-node-id", "body": "Hello Bob!"}
    })
    print(result["output"]["delivered"])  # "queued" or "direct"

    # --- List marketplace posts ---
    result = await node.bus.call("market.list", (1, 0), {"input": {}})
    for post in result["output"]["posts"]:
        print(f"{post['category']}: {post['title']}")

    # --- Discover available capabilities ---
    entries = list(node.bus.registry.all())
    for e in entries:
        print(f"  {e.descriptor.name}@{e.descriptor.version[0]}.{e.descriptor.version[1]}"
              f" on {e.node_id} params={e.descriptor.params}")

asyncio.run(main())
```

**From the CLI (no Python required):**
```bash
# Call any capability from the command line
python -m hearthnet.cli call llm.chat 1 0 \\
  '{"input":{"messages":[{"role":"user","content":"Hello!"}]}}'

python -m hearthnet.cli call rag.query 1 0 \\
  '{"params":{"corpus":"community"},"input":{"query":"emergency water","k":3}}'

python -m hearthnet.cli capabilities   # list all available capabilities
```

---

## Getting Model Weights from a Peer Node

A node **without internet** can pull model weights from any peer that has them.
The weights travel as BLAKE3 content-addressed chunks over the HearthNet transport
(no BitTorrent tracker needed — peers are already known from the mesh):

```python
# Step 1: Find what models a peer has
models = await node.bus.call("model.list", (1, 0), {"input": {}})
for m in models["output"]["models"]:
    print(f"  {m['name']} ({m['size_bytes'] // 1024**2} MB) on {m['node_id']}")

# Step 2: Pull a model from a specific peer
job = await node.bus.call("model.pull", (1, 0), {
    "input": {
        "model_name": "llama3.2:3b",      # name as reported by model.list
        "source_node": "peer-node-id",     # node_id from the list above
        # "dest_dir": "/custom/path"       # optional; default: ~/.hearthnet/blobs/
    }
})
job_id = job["output"]["job_id"]

# Step 3: Poll until complete
import asyncio
while True:
    status = await node.bus.call("model.status", (1, 0), {"input": {"job_id": job_id}})
    pct = status["output"]["progress"] * 100
    print(f"  {pct:.0f}% — {status['output']['state']}")
    if status["output"]["state"] in ("complete", "error"):
        break
    await asyncio.sleep(2)
```

**Notes:**
- Offline nodes can pull from any reachable peer — no internet needed, only LAN
- Files land in `~/.hearthnet/blobs/` (BLAKE3 CID-addressed, never duplicated)
- If Ollama is installed, the model is automatically registered after download
- On HF Space: model.pull works peer-to-peer but the Space has no persistent storage

---

## Connecting Your Local Node to the HF Space

The HF Space is a live single-node HearthNet instance. You can connect your
local node to it and use its SmolLM2-135M or share your local Ollama models
with it:

```bash
# 1. Redeem the HF Space invite
python -m hearthnet.cli invite redeem \\
  "hnvite://v1/hf-space-1c95381d?host=build-small-hackathon-hearthnet.hf.space&port=443&transport=https&level=member"

# 2. Verify peer was added
python -m hearthnet.cli peers
#   hf-space-1c95381d  build-small-hackathon-hearthnet.hf.space:443  [llm.chat, rag.query, ...]

# 3. Route a query — if your Ollama is faster, it answers instead of the Space
python -m hearthnet.cli call llm.chat 1 0 \\
  '{"input":{"messages":[{"role":"user","content":"Hello from the mesh!"}]}}'
```

Or use the connect script (checks both sides):
```bash
python scripts/connect_to_hf.py
```

**What happens after connecting:**
- Your local LLM (if faster/better) will be preferred over the Space's SmolLM2
- Your local RAG corpus is accessible to Space users who query `rag.query`
- Emergency alerts propagate to both the Space and your local node
- Marketplace posts replicate between your node and the Space
""")

