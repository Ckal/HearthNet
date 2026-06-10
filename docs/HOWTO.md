# HearthNet — HOWTO Guide

This document answers the most common setup and usage questions.

---

## Table of Contents

1. [Quick Start (single machine)](#1-quick-start)
2. [Raspberry Pi Setup](#2-raspberry-pi-setup)
3. [How Nodes Discover Each Other](#3-discovery)
4. [Connecting from a Second Device / Browser](#4-multi-device)
5. [Adding Content to the RAG Knowledge Base](#5-rag)
6. [Configuring LLM Backends](#6-llm-backends)
7. [Creating and Managing a Community](#7-community)
8. [Inviting Other Nodes](#8-inviting)
9. [How to Extend HearthNet (developer)](#9-extending)
10. [Troubleshooting](#10-troubleshooting)

---

## 1. Quick Start

```bash
# Install Python 3.11+
pip install -e ".[dev]"

# Start the Gradio UI (opens at http://127.0.0.1:7860)
python app.py

# Or via the CLI:
python -m hearthnet.cli run
```

The node starts with:
- mDNS announcement (LAN discovery)
- UDP multicast announcement (fallback)
- A local-only Gradio UI at http://127.0.0.1:7860
- Demo LLM (echo fallback until a real backend is configured)

---

## 2. Raspberry Pi Setup

HearthNet runs on a Raspberry Pi 4 (4 GB) or Pi 5.

### Recommended model for Pi

**MiniCPM3-4B** via Ollama or llama.cpp — fits in 4 GB RAM.

```bash
# 1. Install on Pi (Raspberry Pi OS 64-bit bookworm)
sudo apt update && sudo apt install python3-pip git -y
git clone https://github.com/HearthNet/hearthnet
cd hearthnet
pip install -e .

# 2. Install Ollama (optional but recommended)
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5:3b          # ~2 GB, fast on Pi 5
# or
ollama pull minicpm3:4b         # if available

# 3. Create config
mkdir -p ~/.hearthnet
cat > ~/.hearthnet/config.toml << 'EOF'
[identity]
auto_generate = true

[transport]
host = "0.0.0.0"     # listen on all interfaces so LAN clients can connect
port = 7080

[discovery]
mdns_enabled = true
udp_enabled  = true

[ui]
host = "0.0.0.0"   # serve Gradio on all interfaces
port = 7860

[[llm.backends]]
name = "ollama"
url  = "http://localhost:11434"
EOF

# 4. Run
python -m hearthnet.cli run
```

Open `http://<pi-ip>:7860` from any browser on the LAN.

### Auto-start on boot (systemd)

```ini
# /etc/systemd/system/hearthnet.service
[Unit]
Description=HearthNet Community AI
After=network.target

[Service]
User=pi
WorkingDirectory=/home/pi/hearthnet
ExecStart=/home/pi/.local/bin/python -m hearthnet.cli run
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable hearthnet
sudo systemctl start hearthnet
```

---

## 3. Discovery

HearthNet uses **three discovery methods** (in priority order):

### mDNS (LAN — automatic)

Every node announces itself as `_hearthnet._tcp.local.` using **Zeroconf**.  
No configuration needed. Works on any LAN where mDNS is not blocked.

```
Node A starts → announces _hearthnet._tcp.local. via mDNS
Node B starts → discovers Node A, sees its capabilities, registers them on its bus
```

### UDP multicast (LAN — fallback)

Uses multicast group `239.255.42.42:42424`.  
Works when mDNS is blocked by a firewall or managed switch.

### Relay tier (WAN — Phase 2)

For nodes behind NAT or across the internet, configure a relay URL:

```toml
[discovery]
relay_urls = ["https://your-relay.example.com"]
```

See [docs/p2_p3/M15-relay-tier.md](p2_p3/M15-relay-tier.md).

### Checking connected peers

**In the UI:** Settings tab → "Connected Peers & Capabilities" → click Refresh.

**Via CLI:**
```bash
python -m hearthnet.cli status
python -m hearthnet.cli caps --remote-only
```

---

## 4. Multi-Device / Multi-Browser

### Two browsers on the same LAN

1. Start HearthNet on one machine with `host = "0.0.0.0"` in `config.toml`
2. Open `http://<machine-ip>:7860` in any browser on the LAN

Both browsers connect to the **same node** — they share the same bus, peer list, and capabilities.

### Two separate nodes (two machines)

1. Machine A: `python -m hearthnet.cli run`
2. Machine B: `python -m hearthnet.cli run`
3. Both must be on the same LAN (mDNS) or share a relay URL

Once discovered, Machine B's bus sees Machine A's capabilities (e.g. `llm.chat@1.0`).  
Calls made from Machine B's UI automatically route to whichever node has the best-scoring provider.

### Testing two clients in one browser (different tabs / incognito)

Each browser tab that opens the Gradio UI is just a view onto the same node.  
To simulate two truly independent clients, run two nodes on different ports:

```bash
# Terminal 1
HEARTHNET_TRANSPORT_PORT=7081 HEARTHNET_UI_PORT=7861 python -m hearthnet.cli run

# Terminal 2
HEARTHNET_TRANSPORT_PORT=7082 HEARTHNET_UI_PORT=7862 python -m hearthnet.cli run
```

Open `http://127.0.0.1:7861` and `http://127.0.0.1:7862` in two browser tabs.  
Both nodes discover each other via mDNS within a few seconds.

### Playwright E2E test for two nodes

```python
# tests/test_e2e_playwright.py already includes:
# - TestUiLoads    — all 6 tabs present
# - TestAskTab     — real LLM/fallback response
# - TestResponsiveLayout — mobile viewport
```

Run:
```bash
python -m pytest tests/test_e2e_playwright.py -v
```

---

## 5. RAG — Adding to the Knowledge Base

### Via the UI (Settings tab → RAG — Ingest Documents)

1. Open the Settings tab
2. Expand "RAG — Ingest Documents"
3. Enter a corpus name (default: `community`)
4. Upload a `.txt`, `.md`, or `.pdf` file
5. Click **Ingest**

The document is chunked (1000 tokens, 200-token overlap), embedded, and stored in ChromaDB.

### Via CLI

```bash
python -m hearthnet.cli rag ingest ./docs/emergency-procedures.md --corpus community
python -m hearthnet.cli rag ingest ./manuals/first-aid.pdf --corpus medical

# List corpora
python -m hearthnet.cli rag list
```

### Via the bus (programmatic)

```python
result = await bus.call(
    "rag.ingest", (1, 0),
    {"input": {
        "corpus": "community",
        "doc_title": "Emergency procedures",
        "text": "... full document text ...",
    }}
)
```

### Using RAG in the Ask tab

Select a corpus from the dropdown in the Ask tab. HearthNet retrieves  
the top-k most relevant chunks and provides them as context to the LLM.

---

## 6. LLM Backends

HearthNet tries backends in this order:

| Priority | Backend | When to use |
|----------|---------|-------------|
| 1 | **Ollama** | Best UX. Zero-config. `ollama serve` + `ollama pull <model>` |
| 2 | **llama.cpp HTTP** | Direct GPU control. Start with `./server -m model.gguf` |
| 3 | **OpenBMB / MiniCPM** | Small local models (4–8B). Pi-friendly |
| 4 | **Nemotron** | NVIDIA cloud or NIM server |
| 5 | **Generic OpenAI-compat** | LM Studio, vLLM, any OpenAI-compatible server |
| 6 | **HF Transformers** | Last resort local inference |

Cloud APIs (OpenAI, Nemotron cloud) are **never the default** — they require explicit config and are automatically deregistered when the node goes offline.

### Ollama (recommended)

```bash
# Install: https://ollama.com
ollama pull llama3.2:3b      # 2 GB — works on 4 GB RAM
ollama pull qwen2.5:7b       # 5 GB — good quality
ollama pull minicpm3:4b      # 3 GB — Pi-friendly
```

```toml
[[llm.backends]]
name = "ollama"
url  = "http://localhost:11434"
```

### llama.cpp HTTP server

```bash
./server -m models/qwen2.5-7b-q4_k_m.gguf --port 8080 -c 4096
```

```toml
[[llm.backends]]
name  = "llama_cpp"
url   = "http://localhost:8080"
model = "qwen2.5-7b"
```

### OpenBMB MiniCPM (via vLLM)

```bash
vllm serve openbmb/MiniCPM4-8B --port 8000
```

```toml
[[llm.backends]]
name  = "openbmb"
url   = "http://localhost:8000"
model = "openbmb/MiniCPM4-8B"
```

### Nemotron (cloud or NIM)

```bash
export NVIDIA_API_KEY=nvapi-xxx
```

```toml
[[llm.backends]]
name        = "nemotron"
url         = "https://integrate.api.nvidia.com/v1"
model       = "nvidia/nemotron-mini-4b-instruct"
api_key_env = "NVIDIA_API_KEY"
```

---

## 7. Creating and Managing a Community

A **community** is a signed group manifest with member trust levels.

### Create a new community

```bash
python -m hearthnet.cli init --name "My Neighborhood" --profile anchor
```

This:
1. Generates Ed25519 keys in `~/.hearthnet/keys/`
2. Creates a community manifest signed by the root key
3. Writes `~/.hearthnet/config.toml`

### Join an existing community

```bash
python -m hearthnet.cli invite redeem "hnvite://v1/..."
```

### Check community status

```bash
python -m hearthnet.cli status
```

---

## 8. Inviting Other Nodes

### Generate an invite link (UI)

Settings tab → "Invite a Node" → enter trust level → click **Generate Invite Link**.

### Generate an invite link (CLI)

```bash
python -m hearthnet.cli invite create --node-id ed25519:xxx --level member
# Prints: hnvite://v1/...
```

### Redeem on the new node

```bash
python -m hearthnet.cli invite redeem "hnvite://v1/..."
```

### Mobile (M22)

The mobile app (Flutter) can scan a QR code displayed by:

```bash
python -m hearthnet.cli invite create --qr
```

Or via the Settings tab → Invite a Node → the link can be pasted into the app's  
"Join Community" screen.

---

## 9. Extending HearthNet

### Adding a new capability (service)

1. Create `hearthnet/services/myservice/service.py`

```python
# Spec reference: docs/M03-bus.md §4 (Service Protocol)
from hearthnet.services.base import Service
from hearthnet.bus.capability import CapabilityDescriptor, RouteRequest

class MyService(Service):
    name = "myservice"
    version = "1.0"

    def capabilities(self):
        desc = CapabilityDescriptor(
            name="myservice.do@1.0",
            version=(1, 0),
            stability="beta",
            request_schema={},
            response_schema=None,
            stream_schema=None,
            params={},
            max_concurrent=4,
            trust_required="member",
            timeout_seconds=30,
            idempotent=True,
        )
        return [(desc, self.handle_do, None)]

    async def handle_do(self, req: RouteRequest) -> dict:
        inp = req.body.get("input", {})
        return {"output": {"result": f"processed: {inp}"}, "meta": {}}

    async def start(self): pass
    async def stop(self): pass
    def health(self): return {"status": "ok"}
```

2. Register with the bus in `hearthnet/node.py`:

```python
from hearthnet.services.myservice.service import MyService
bus.register_service(MyService())
```

3. Add tests in `tests/test_myservice.py`.

### Adding a new LLM backend

Implement `LlmBackend` (Protocol in `hearthnet/services/llm/backends/base.py`):

```python
# Spec: docs/M04-llm.md §3.1
class MyLlmBackend:
    name = "myllm"
    models = [BackendModel(name="my-model", family="local", context_length=8192, requires_internet=False)]

    async def chat(self, messages, *, model, stream=False, temperature=0.7, max_tokens=1024, **kw):
        ...  # call your server, return ChatResult or AsyncIterator[Token]

    async def complete(self, prompt, *, model, **kw): ...
    async def warm(self): pass
    async def close(self): pass
    def health(self): return {"status": "ok"}
```

Then register it in `LlmService.__init__` alongside the other backends.

### Adding a new UI tab

1. Create `hearthnet/ui/tabs/mytab.py`

```python
# Spec: docs/M08-ui.md §5
def build_mytab(bus=None):
    import gradio as gr
    with gr.Column():
        gr.Markdown("### My Tab")
        ...
```

2. Add it to `hearthnet/ui/app.py` inside the `gr.Tabs()` block:

```python
with gr.Tab("MyTab"):
    from hearthnet.ui.tabs.mytab import build_mytab
    build_mytab(self._bus)
```

---

## 10. Troubleshooting

### No LLM responses

1. Check Ollama is running: `ollama list`
2. Check `python -m hearthnet.cli doctor`
3. Check `python -m hearthnet.cli caps` — does `llm.chat@1.0` appear?

### Peers not discovered

1. Are both machines on the same LAN subnet?
2. Is mDNS blocked? Try enabling UDP fallback in config
3. `python -m hearthnet.cli status` — what does it show?

### RAG returns no results

1. Did you ingest documents? Settings tab → RAG — Ingest Documents
2. `python -m hearthnet.cli rag list` — are corpora listed?
3. Embedding model must be loaded — check `python -m hearthnet.cli doctor`

### Config file location

```
~/.hearthnet/config.toml   (Linux/macOS)
%USERPROFILE%\.hearthnet\config.toml   (Windows)
```

### Log files

```bash
python -m hearthnet.cli log --follow
# Or look at:
~/.hearthnet/logs/hearthnet.log
```

### Emergency mode stuck "offline"

```bash
# Force a connectivity check:
python -m hearthnet.cli call emergency.probe@1.0 '{}'
# Or in UI: Emergency tab → Run Connectivity Probe
```
