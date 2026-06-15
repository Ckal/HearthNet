# HearthNet — Environment Variables, Secrets & Models Reference

*Last updated: June 15, 2026*

---

## Quick Start: Minimum required for HF Space

```
NVIDIA_API_KEY = nvapi-...          # enables Nemotron + NVIDIA prize track
HEARTHNET_DATA_DIR = /data/hearthnet  # persistent storage (needs Persistent Storage enabled)
```

Everything else has sensible defaults.

---

## All Environment Variables

### 🔴 Secrets (never commit, use HF Space secrets)

| Variable | Purpose | Example |
|----------|---------|---------|
| `NVIDIA_API_KEY` | NVIDIA NIM API key — activates NemotronBackend, enables all `nvidia/*` models. Get free at [build.nvidia.com](https://build.nvidia.com) | `nvapi-abc123...` |
| `MODAL_TOKEN` | Modal API token — needed only if `modal deploy` is used. Set automatically by Modal CLI. | `ak-...` |
| `HEARTHNET_HF_TOKEN` | HuggingFace Inference API token — activates `HfApiBackend` for cloud inference. Get at [hf.co/settings/tokens](https://huggingface.co/settings/tokens) | `hf_abc...` |
| `ANTHROPIC_API_KEY` | Anthropic Claude API — activates `AnthropicBackend`. Not used by default. | `sk-ant-...` |

### 🟡 Configuration (safe to set in Space settings, not truly secret)

| Variable | Default | Purpose | Where read |
|----------|---------|---------|-----------|
| `MODEL_ID` | `openbmb/MiniCPM3-4B` | HF Transformers model to load locally | `app.py:49` |
| `MODEL_REVISION` | `None` | Model git revision/hash to pin | `app.py:50` |
| `HEARTHNET_DATA_DIR` | `tempfile.gettempdir()` | Base directory for RAG corpora, BLAKE3 blobs, relay DB. Set to `/data/hearthnet` when Persistent Storage is enabled on the Space. | `app.py:352` |
| `SPACE_TITLE` | `HearthNet Space (xxxx)` | Display name shown in the UI header and relay roster | `app.py:186` |
| `MODAL_ENDPOINT` | `""` | URL of deployed Modal LLM endpoint — activates `ModalBackend` | `app.py:273` |
| `MODAL_MODEL` | `HuggingFaceTB/SmolLM2-1.7B-Instruct` | Model served by the Modal endpoint | `modal_backend.py:65` |
| `MINICPM_URL` | `""` | OpenAI-compatible endpoint for a local/remote MiniCPM vLLM server | `app.py:287` |
| `MINICPM_MODELS` | `""` | Comma-separated model names exposed by `MINICPM_URL` | `app.py:292` |
| `MINICPM_LIGHTWEIGHT` | `""` | Set to `1` or `true` to force SmolLM2-135M instead of MiniCPM3-4B | `app.py:294` |
| `NEMOTRON_URL` | `""` | Local NVIDIA NIM endpoint (e.g. `http://localhost:8000`) — used by both `app.py` and `app_nemotron.py` | `app_nemotron.py:31` |
| `HEARTHNET_NODE` | `""` | URL of a HearthNet mesh node to connect to (used by `app_nemotron.py` Push-to-Mesh tab) | `app_nemotron.py:29` |
| `PORT` | `7869` | Port for `app_nemotron.py` standalone server | `app_nemotron.py:506` |
| `SPACE_HOST` | `""` | Auto-set by HF — used internally to detect ZeroGPU context | `app.py:181` |
| `GRADIO_SSR_MODE` | `false` | Forced to `false` to prevent Node.js intercepting custom FastAPI routes | `app.py:565` |

---

## All Models

### Prize Track Mapping

| Prize | Requirement | Models to Use |
|-------|-------------|--------------|
| 🐜 **Tiny Titan** | ≤ 32B parameters | MiniCPM3-4B (4B) ✅, SmolLM2-135M (135M) ✅, Nemotron-nano-8B (8B) ✅ |
| 🔬 **NVIDIA Nemotron** | Use Nemotron models | `nvidia/llama-3.1-nemotron-nano-8b-instruct` ✅ |
| 🏭 **OpenBMB** | Use MiniCPM models | `openbmb/MiniCPM3-4B` ✅, `openbmb/MiniCPM4-8B` ✅ |
| ⚡ **Modal** | Deploy on Modal | Any model via `scripts/modal_deploy.py` ✅ |
| 🎨 **Off Brand** | Custom UI/theme | Custom CSS + purple gradient ✅ |

### Models by Backend

#### Local (runs on HF Space / Pi / laptop)

| Model | Size | Backend | Set via | Notes |
|-------|------|---------|---------|-------|
| `openbmb/MiniCPM3-4B` | **4B** | `HfLocalBackend` | `MODEL_ID` env | **Default**. OpenBMB + Tiny Titan eligible |
| `HuggingFaceTB/SmolLM2-135M-Instruct` | **135M** | `HfLocalBackend` | `MODEL_ID=HuggingFaceTB/SmolLM2-135M-Instruct` | Pi Zero / ultra-light mode |
| `HuggingFaceTB/SmolLM2-1.7B-Instruct` | **1.7B** | `HfLocalBackend` | `MODEL_ID=...` | Good balance on CPU |
| `openbmb/MiniCPM4-8B` | **8B** | `HfLocalBackend` | `MODEL_ID=openbmb/MiniCPM4-8B` | Faster than MiniCPM3, better quality |
| `openbmb/MiniCPM-V-2_6` | **8B** | `HfLocalBackend` | `MODEL_ID=openbmb/MiniCPM-V-2_6` | **Multimodal** — vision + text |

#### NVIDIA NIM (cloud — needs `NVIDIA_API_KEY`)

| Model | Size | Prize eligible | Best for |
|-------|------|---------------|---------|
| `nvidia/llama-3.1-nemotron-nano-8b-instruct` | **8B** | Tiny Titan ✅ | Fast, edge reasoning |
| `nvidia/nemotron-mini-4b-instruct` | **4B** | Tiny Titan ✅ | Smallest Nemotron |
| `nvidia/nemotron-3-nano-30b-a3b` | 30B MoE (3B active) | Tiny Titan ✅ | MoE routing brain |
| `nvidia/llama-3.3-nemotron-super-49b-v1` | 49B | NVIDIA track | Best reasoning |
| `nvidia/llama-3.1-nemotron-70b-instruct` | 70B | NVIDIA track | Highest quality |
| `nvidia/nemotron-nano-12b-v2-vl` | 12B | Tiny Titan ✅ | **Vision-language** |

> **Contest note:** For Tiny Titan prize (≤32B), use: nano-8B, nano-4B, nano-30B-a3b, or nano-12b-v2-vl.
> The 49B and 70B models exceed the 32B limit and only qualify for the main Nemotron hardware prize.

#### OpenBMB (cloud — needs `MINICPM_URL` pointing to a vLLM server)

| Model | Size | Notes |
|-------|------|-------|
| `openbmb/MiniCPM4-8B` | 8B | Best OpenBMB model for 2026 |
| `openbmb/MiniCPM3-4B` | 4B | Default, runs locally |

#### Modal (serverless GPU — needs `MODAL_ENDPOINT`)

| Model | Size | Set via |
|-------|------|---------|
| `HuggingFaceTB/SmolLM2-1.7B-Instruct` | 1.7B | Hardcoded in `scripts/modal_deploy.py:23` |
| Any HF model | — | Change `MODEL_ID` in `scripts/modal_deploy.py` and redeploy |

#### Other (cloud)

| Backend | Model | Needs |
|---------|-------|-------|
| `HfApiBackend` | `HuggingFaceH4/zephyr-7b-beta` | `HEARTHNET_HF_TOKEN` |
| `AnthropicBackend` | `claude-3-haiku-20240307` | `ANTHROPIC_API_KEY` |

---

## Recommended Configurations

### HF Space (current, contest submission)
```
MODEL_ID = openbmb/MiniCPM3-4B          # OpenBMB + Tiny Titan prizes
NVIDIA_API_KEY = nvapi-...               # Nemotron Hardware Prize
HEARTHNET_DATA_DIR = /data/hearthnet     # Persistent Storage (if enabled)
SPACE_TITLE = HearthNet                  # Display name
```

### Pi Zero / Ultra-Light Mode
```
MODEL_ID = HuggingFaceTB/SmolLM2-135M-Instruct   # 135M, fits in 512MB RAM
MINICPM_LIGHTWEIGHT = 1
```

### Full Local Stack (laptop/desktop)
```
MODEL_ID = openbmb/MiniCPM4-8B          # Best local model
NVIDIA_API_KEY = nvapi-...               # For Nemotron fallback
NEMOTRON_URL = http://localhost:8000     # Local NIM server (optional)
HEARTHNET_DATA_DIR = ~/.hearthnet/data   # Persistent local data
```

### With Modal GPU Backend
```
MODAL_ENDPOINT = https://your-org--hearthnet-llm-chat.modal.run
# Deploy first: modal deploy scripts/modal_deploy.py
```

---

## HF Space Secrets Checklist

```
[x] NVIDIA_API_KEY        — free at build.nvidia.com, no credit card
[ ] HEARTHNET_DATA_DIR    — set to /data/hearthnet after enabling Persistent Storage
[ ] SPACE_TITLE           — optional display name override
[ ] MODAL_ENDPOINT        — after running: modal deploy scripts/modal_deploy.py
[ ] MINICPM_URL           — if running a separate vLLM server with MiniCPM4-8B
```

---

## Model Size Quick Reference

```
SmolLM2-135M      ████░░░░░░░░░░░░░░░░  135M    — Pi Zero, embedded
MiniCPM3-4B       ████████░░░░░░░░░░░░  4B      — Default ★
SmolLM2-1.7B      █████████░░░░░░░░░░░  1.7B    — CPU laptop
Nemotron-nano-4B  ████████░░░░░░░░░░░░  4B      — Tiny Titan ★
MiniCPM4-8B       ████████████░░░░░░░░  8B      — Best quality local
Nemotron-nano-8B  ████████████░░░░░░░░  8B      — Tiny Titan ★
Nemotron-12B-VL   █████████████████░░░  12B     — Vision+text
Nemotron-30B-a3b  ██████████████░░░░░░  30B MoE (3B active) — Tiny Titan ★
                                ↑ 32B Tiny Titan limit ↑
Nemotron-Super-49B███████████████████░  49B     — NVIDIA prize only
Nemotron-70B      ████████████████████  70B     — NVIDIA prize only
```
