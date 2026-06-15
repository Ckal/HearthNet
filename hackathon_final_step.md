# HearthNet — Project Status

*Consolidated June 15, 2026 · Build Small Hackathon · merged from tasks.md*

---

## What Was Built

**489 tests, 0 failures.** All Phase 1 (M01–M13, X01–X04), Phase 2 (M14–M25, X05–X07),
and Phase 3 experimental (M26–M31) modules implemented.
See [ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full module map and data flows.

| Phase | Modules | Status |
|-------|---------|--------|
| Phase 1 | M01 Identity · M02 Discovery · M03 Bus · M04 LLM · M05 RAG · M06 Marketplace · M07 Files · M08 UI · M09 Emergency · M10 Chat · M11 Embedding · M12 CLI · M13 Onboarding · X01–X04 | ✅ Complete |
| Phase 2 | M14 Federation · M15 Relay · M16 Tokens · M17 OCR · M18 Translation · M19 STT/TTS · M20 Vision · M21 Tools · M22 Mobile · M23 E2E Crypto · M24 Rerank · M25 Group Chat · X05–X07 | ✅ Complete |
| Phase 3 | M26 Distributed inference · M27 MoE · M28 Fedlearn · M29 LoRa · M30 Evidence · M31 Civil Defense | ✅ Registered (compute stubs — see Remaining Gaps) |

**Internet mesh (relay hub, P1–P3):** `CompositeTransport` + `RelayHub` + `RelayClient`
with SQLite-backed roster persistence. All-to-all over a real uvicorn relay.
Tests: `tests/test_relay_mesh.py` (all pass).

**Security audit (June 12):** CVE-2025-3000 (PyTorch) and CVE-2025-71176 (pytest) patched.
`florence2.py` trust_remote_code allowlist added. Full report: [SECURITY_AUDIT_ASSESSMENT.md](SECURITY_AUDIT_ASSESSMENT.md).

---

## Bugs Fixed (June 14)

| Fix | File |
|-----|------|
| FIX-1: `node.start()` never set `_started = True` → `stop()` silently no-oped | `hearthnet/node.py` |
| FIX-2: `ChatService.send()` swallowed all exceptions silently | `hearthnet/services/chat/service.py` |
| FIX-3: `UTC = UTC` dead re-assignment (copy-paste artifact) | `chat/service.py`, `marketplace/service.py` |
| FIX-4: `RagService` defaulted `corpora_dir` to cwd instead of `~/.hearthnet/corpora` | `hearthnet/services/rag/service.py` |
| FIX-5: Seed corpus never ingested — `handle_ingest` ignored `{"documents": [...]}` batch format | `service.py`, `app.py` |
| FIX-6: `asyncio.run(_seed_corpus())` raised RuntimeError when loop already running | `app.py` |
| FIX-7: `app.py` created `RagService` without `corpora_dir` → corpus written to cwd | `app.py` |
| FIX-8: `Router._sticky` dict grew unbounded (memory leak) | `hearthnet/bus/router.py` |

**15 additional targeted improvements (June 15):**
RAG SQLite persistence, bus failover for quarantined providers, brace-matching JSON parser
in agent, MoE expert self-registration, schema_hash prefix fix (`sha256:`),
corpus param plumbing, federated_query wiring, silent exception sweep.
See `tests/test_improvements_batch.py` (13 tests, all pass).

---

## Hackathon Prize Status

| # | Action | Status |
|---|--------|--------|
| P1 | Demo video recorded | ✅ Done |
| P2 | Social post on X @zX14_7 | ✅ Done |
| P3 | NVIDIA_API_KEY set in HF Space secrets | ✅ Done |
| P4 | Deploy `app_nemotron.py` as second HF Space | ✅ Done — `feat/nemotron-space` branch → `build-small-hackathon/HearthNet-Nemotron` |
| P5 | MiniCPM3-4B as default model (OpenBMB prize) | ✅ Done — `MODEL_ID` default changed in `app.py` |
| P6 | `modal deploy scripts/modal_deploy.py` | ✅ Done — `scaledown_window` fix applied |
| P7 | GitHub Codex commits | ✅ Done |

**HF Spaces:**
- Main: `https://huggingface.co/spaces/build-small-hackathon/HearthNet` (`app.py`, MiniCPM3-4B default)
- Nemotron: `https://huggingface.co/spaces/build-small-hackathon/HearthNet-Nemotron` (`app_nemotron.py`, SmolLM2 fallback when no API key)

---

## Genuine Remaining Gaps

### Real stubs / not implemented

| Location | Gap | Effort |
|----------|-----|--------|
| `hearthnet/distributed_inference/shard.py:75` | `ShardServer.forward()` raises `NotImplementedError` — needs torch model-slicing | High (M26 roadmap) |
| `hearthnet/distributed_inference/pipeline.py:84` | `PipelineOrchestrator.run()` raises `NotImplementedError` — M26 experimental | High |
| `hearthnet/lora/service.py:96` | `_transmit()` stub — skips silently without pyserial hardware | Medium (M29, hardware-gated) |
| `hearthnet/services/marketplace/service.py:81` | Falls to "demo mode" on any event_log exception — silent degradation | Low |
| M28 | `FedLearnCoordinator` compute path — peft gradient aggregation not wired | High |
| M23 | X3DH / Double Ratchet E2E encryption **implemented but not wired as default** in chat | Medium |

### Healthy degradation (not bugs)

All `backend_unavailable` responses in OCR / STT / TTS / Translation / Image services
are intentional: optional deps absent → clear error message, no silent failure.
`_UnavailableBackend` in LlmService is the correct fallback when no backends are loaded.

### P4 browser–Python bridge (deferred)

Browser mesh (`webagent/src/mesh/browsermesh.js`, PeerJS/WebRTC) and the Python relay
currently run as separate meshes. Bridging them (bidirectional WebRTC↔mailbox
translation, ICE/TURN) is deferred — P1–P3 relay proven first.

---

## Post-Hackathon Roadmap

```
[ ] pip install hearthnet         — pyproject.toml ready; not yet on PyPI
[ ] M26 ShardServer.forward()     — real torch sharding
[ ] M28 Federated learning        — peft gradient aggregation
[ ] M29 LoRa hardware             — pyserial serial port integration
[ ] M23 E2E chat encryption       — wire X3DH/Double Ratchet as default
[ ] Browser↔Python mesh bridge    — P4 internet mesh
[ ] Custom non-Gradio UI          — modern HTML/CSS alongside reference UI
[ ] Docker image publish          — Dockerfile.slim exists, CI publish pending
```

---

## Deployment Checklist

```
[x] NVIDIA_API_KEY secret → Nemotron backend auto-activates
[x] HEARTHNET_DATA_DIR set → persistent data survives Space restarts
[x] ZeroGPU Space confirmed
[x] Demo video URL in README
[x] Social post URL in README
[ ] MODAL_ENDPOINT secret → set after `modal deploy scripts/modal_deploy.py`
[ ] MINICPM_URL secret → optional vLLM/llama.cpp endpoint for external MiniCPM server
```
