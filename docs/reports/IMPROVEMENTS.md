# HearthNet — Improvements & Gaps

*Updated June 15, 2026 · post-hackathon audit*

---

## GPT-4o "Judge" Rating

| Dimension | Score | Notes |
|-----------|-------|-------|
| **Innovation** | 9/10 | P2P AI mesh is genuinely novel |
| **Implementation depth** | 9/10 | 31 real modules, 489 tests, real crypto, real event log |
| **Tiny-ness** | 10/10 | MiniCPM3-4B default; SmolLM2-135M on Pi |
| **Hackathon compliance** | 10/10 | Video ✅ Social ✅ NVIDIA key ✅ Nemotron Space ✅ |
| **UX / demo quality** | 8/10 | Nemotron + Voice tabs added. Missing STT/TTS UI was gap |
| **Documentation** | 9/10 | Excellent README, architecture diagram, 17 spec docs |
| **Prize targeting** | 9/10 | Nemotron + MiniCPM + Modal + SmolLM2 all wired |
| **Overall** | **9.1 / 10** | All critical items done. Remaining gaps are research/optional |

---

## 🚨 CRITICAL — all done ✅

| Item | Status |
|------|--------|
| C1 Demo video | ✅ Done |
| C2 Social post on X | ✅ Done |
| C3 NVIDIA API key in HF Space secrets | ✅ Done |

---

## 🏆 HIGH IMPACT — all done ✅

| Item | Status |
|------|--------|
| H1 Deploy `app_nemotron.py` as second HF Space | ✅ `build-small-hackathon/HearthNet-Nemotron` live |
| H2 MiniCPM3-4B as default model | ✅ `MODEL_ID` default changed in `app.py` |
| H3 Modal endpoint | ✅ `scaledown_window` fix in `scripts/modal_deploy.py` |
| H4 GitHub Codex commits | ✅ Done |
| H5 Nemotron UI polish | ✅ Purple-to-yellow gradient, SmolLM2 fallback |

---

## 🔌 WIRED UP (June 15) — previously hidden

These were implemented but disconnected. All now wired:

| Fix | What | Files Changed |
|-----|------|---------------|
| W1 | **Nemotron tab** added to main Gradio UI | `hearthnet/ui/app.py` |
| W2 | **Voice tab** (STT + TTS) added to main Gradio UI | `hearthnet/ui/tabs/voice.py` (new), `ui/app.py` |
| W3 | **FederationService** (M14) registered in `install_services()` | `hearthnet/node.py` |
| W4 | **ImageGenerateService** now gets Florence2Backend at init — was empty list | `hearthnet/node.py` |
| W5 | **edge-tts, faster-whisper, pytesseract** added to `requirements.txt` | `requirements.txt` |
| W6 | `/data` permission check — graceful fallback to tmpdir if not mounted | `app.py` |

---

## 🔧 REMAINING TECHNICAL GAPS

### Real stubs / NotImplementedError

| Location | Gap | Effort |
|----------|-----|--------|
| `hearthnet/distributed_inference/shard.py:75` | `ShardServer.forward()` — torch model-slicing not implemented (M26) | High |
| `hearthnet/distributed_inference/pipeline.py:84` | `PipelineOrchestrator.run()` — M26 experimental | High |
| `hearthnet/fedlearn/coordinator.py:95` | `FedLearnCoordinator.aggregate()` — peft gradient aggregation not wired (M28) | High |
| `hearthnet/lora/service.py:96` | `_transmit()` — silently skips without pyserial hardware (M29) | Medium |
| `hearthnet/discovery/relay.py:8` | `RelayDiscovery.start()` — Phase 2 relay-based peer discovery never implemented | High |

### Healthy degradation (intentional, not bugs)

All of these return a clear `{"error": "backend_unavailable"}` when optional deps are absent:

| Service | Capability | Fallback |
|---------|-----------|---------|
| `OcrService` | `ocr.image` / `ocr.pdf` | TrOCR → Tesseract → error |
| `TranslationService` | `trans.text` | NLLB-200 → error |
| `SttService` | `stt.transcribe` | faster-whisper → openai-whisper → error |
| `TtsService` | `tts.synthesize` | edge-tts → error |
| `RerankService` | `rerank.text` | BGE → CrossEncoder → error |
| `EmbeddingService` | `embed.text` | SentenceTransformer → SimpleHash (non-semantic) |
| `ImageDescribeService` | `img.describe` | Florence2 → error |
| `ImageGenerateService` | `img.generate` | Florence2 → error |

### Research-gated services (M26-M31, behind `install_extended_services(research=True)`)

| Service | Capability | Status |
|---------|-----------|--------|
| `EvidenceService` | `evidence.claim.*` | Registered in app.py HF Space only; no UI tab |
| `CivilDefenseService` | `civdef.alert.*` | Registered in node.py; no UI tab |
| `LoraBeaconService` | `lora.beacon.*` | Hardware-gated (pyserial + 868 MHz hardware) |

### Not wired in UI (services exist, no tab/button)

| Service | Capability | Missing |
|---------|-----------|---------|
| `ImageDescribeService` | `img.describe` | No UI tab to upload image |
| `OcrService` | `ocr.image` | No UI tab to upload scan |
| `TranslationService` | `trans.text` | No UI tab |
| `EvidenceService` | `evidence.claim.*` | No UI tab |
| `CivilDefenseService` | `civdef.*` | No UI tab |
| Webagent | `GET /webagent/` | Present at `/webagent/` route; not linked from UI |

### Encryption not defaulted (M23)

X3DH / Double Ratchet E2E encryption is implemented in `hearthnet/crypto/` but
chat messages are sent unencrypted by default. Wiring it requires threading the
ratchet state through `ChatService.send()`.

### Browser ↔ Python mesh bridge (P4 — deferred)

Browser mesh (`webagent/src/mesh/browsermesh.js`, PeerJS/WebRTC) and the Python relay
run as separate meshes. Bridging them (bidirectional WebRTC↔mailbox translation) is deferred.

---

## 🎨 UI/UX GAPS

| Item | Effort | Impact |
|------|--------|--------|
| U1 Image tab — upload → `img.describe` via Florence2 | Low | Medium |
| U2 OCR tab — upload scan/PDF → `ocr.image` | Low | Medium |
| U3 Translation tab — text + language pair → `trans.text` | Low | Low |
| U4 Evidence tab — claim / attest / dispute | Medium | Low |
| U5 Routing trace visualisation (Mermaid flow chart) | Medium | Medium |
| U6 Peer capability matrix table in Mesh tab | Low | Medium |
| U7 Dark mode toggle | Low | Low |
| U8 Mobile-responsive CSS | Medium | Low |

---

## 📊 TESTING GAPS

| Item | File | Note |
|------|------|------|
| Q1 Voice tab integration test | `tests/test_voice_tab.py` | Test STT/TTS bus round-trip |
| Q2 Nemotron tab test (mock API) | `tests/test_nemotron_tab.py` | Mock NVIDIA API response |
| Q3 Federation round-trip test | `tests/test_federation_wired.py` | peer.add / peer.list |
| Q4 Image generate with Florence2 | `tests/test_image_generate.py` | Florence2 backend registered |

---

## 🔐 SECURITY GAPS

| Item | File | Fix |
|------|------|-----|
| S1 Rate limiting | `backpressure.py:RateLimiter` | Wire into FastAPI routes |
| S2 Capability token expiry | `hearthnet/tokens/service.py` | `exp` stored but not checked by router |
| S3 E2E encryption default | `hearthnet/crypto/` | Not wired as default in `ChatService.send()` |

---

## 🌍 COMMUNITY / DEPLOYMENT GAPS

| Item | Effort | Notes |
|------|--------|-------|
| D1 `pip install hearthnet` on PyPI | Low | `pyproject.toml` ready; not yet uploaded |
| D2 Docker image publish | Low | `Dockerfile.slim` exists; CI publish pending |
| D3 Raspberry Pi one-command install | Medium | systemd service script needed |
| D4 Home Assistant custom component | High | HA YAML → HearthNet bus bridge |

---

## Post-Hackathon Roadmap

```
[ ] pip install hearthnet         — pyproject.toml ready; not yet on PyPI
[ ] Image / OCR / Translation UI  — tabs for img.describe, ocr.image, trans.text
[ ] M26 ShardServer.forward()     — real torch sharding
[ ] M28 Federated learning        — peft gradient aggregation
[ ] M29 LoRa hardware             — pyserial serial port integration
[ ] M23 E2E chat encryption       — wire X3DH/Double Ratchet as default
[ ] Browser↔Python mesh bridge    — P4 internet mesh via WebRTC
[ ] Custom non-Gradio UI          — modern HTML/CSS alongside reference UI
[ ] Docker image publish          — Dockerfile.slim exists, CI publish pending
```
