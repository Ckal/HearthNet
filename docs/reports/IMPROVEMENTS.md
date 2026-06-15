# HearthNet — Master Task & Improvement List

*Updated June 15, 2026 · Priority order: highest impact first*

---

## ✅ DONE — Hackathon Critical

| # | Task | Commit |
|---|------|--------|
| C1 | Demo video recorded and linked in README | ee40c33 |
| C2 | Social post on X @zX14_7 | ee40c33 |
| C3 | NVIDIA_API_KEY set in HF Space secrets | — |
| C4 | Deploy `app_nemotron.py` as second HF Space (`HearthNet-Nemotron`) | feat/nemotron-space |
| C5 | MiniCPM3-4B as default model in main Space (OpenBMB + Tiny Titan) | ee40c33 |
| C6 | Modal deploy fix — `scaledown_window` replacing deprecated param | ee40c33 |
| C7 | GitHub Codex commits pushed | ee40c33 |
| C8 | NVIDIA API key removed from Gradio frontend (SEC-1 critical fix) | 1c211eb |
| C9 | `/data` permission graceful fallback — Space no longer crashes | c9bf597 |

---

## ✅ DONE — Services Wired Up

Previously implemented in code but never connected or visible:

| # | Task | What was broken | Commit |
|---|------|----------------|--------|
| W1 | Nemotron tab added to main Gradio UI | `nemotron.py` existed, never imported | c021486 |
| W2 | Voice tab (STT + TTS) — new `voice.py` | STT/TTS services registered but no UI | c021486 |
| W3 | FederationService (M14) registered in `install_services()` | Never registered anywhere | c021486 |
| W4 | ImageGenerateService gets Florence2Backend at init | Was instantiated with empty `backends=[]` | c021486 |
| W5 | `edge-tts`, `faster-whisper`, `pytesseract` added to requirements | Not in requirements, so backends silently failed | c021486 |
| W6 | HearthNet theme applied to main app (purple/dark) | `hearthnet_theme` defined but never passed to `gr.Blocks` | latest |
| W7 | Custom CSS header, badges, animated status dot, button hover | Main app had zero custom styling | latest |
| W8 | Voice tab asyncio pattern fixed for Gradio async context | `get_event_loop()` fails inside Gradio's running loop | latest |

---

## 🔴 P0 — Must fix before next demo

### P0-1 — Image tab: upload → Florence2 describe
**Impact:** Shows off Florence2 + vision capability — judge can upload a photo and see AI describe it
**Effort:** 1 hour
**File to create:** `hearthnet/ui/tabs/image.py`
**Capability:** `img.describe@1.0`
**Add to `ui/app.py`:** `from hearthnet.ui.tabs.image import build_image_tab` + `with gr.Tab("🖼 Image"): build_image_tab(bus)`

```python
# Minimal implementation:
def build_image_tab(bus):
    img_input = gr.Image(type="filepath", label="Upload image")
    describe_btn = gr.Button("🔍 Describe with Florence2", variant="primary")
    description_out = gr.Textbox(label="Description", lines=4)

    def _describe(path):
        import base64
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        result = _run(bus.call("img.describe", (1,0), {"input": {"image_b64": b64}}))
        return result.get("output", {}).get("caption", result.get("caption", str(result)))

    describe_btn.click(_describe, inputs=[img_input], outputs=[description_out])
```

### P0-2 — OCR tab: upload scan/PDF → text
**Impact:** Tesseract/TrOCR — a common real-world need
**Effort:** 45 min
**File to create:** `hearthnet/ui/tabs/ocr.py`
**Capability:** `ocr.image@1.0`, `ocr.pdf@1.0`

```python
def build_ocr_tab(bus):
    ocr_input = gr.File(label="Upload image or PDF", file_types=[".png",".jpg",".pdf"])
    ocr_btn = gr.Button("📄 Extract Text", variant="primary")
    ocr_out = gr.Textbox(label="Extracted text", lines=10)

    def _ocr(file_path):
        cap = "ocr.pdf" if file_path.endswith(".pdf") else "ocr.image"
        import base64
        with open(file_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        result = _run(bus.call(cap, (1,0), {"input": {"file_b64": b64}}))
        return result.get("output", {}).get("text", str(result))

    ocr_btn.click(_ocr, inputs=[ocr_input], outputs=[ocr_out])
```

### P0-3 — Translation tab: text + language → translated text
**Impact:** NLLB-200 covers 200 languages — real differentiator
**Effort:** 30 min
**File to create:** `hearthnet/ui/tabs/translation.py`
**Capability:** `trans.text@1.0`

```python
def build_translation_tab(bus):
    src_text = gr.Textbox(label="Text to translate", lines=5)
    src_lang = gr.Textbox(label="Source language", value="en")
    tgt_lang = gr.Textbox(label="Target language", value="de")
    translate_btn = gr.Button("🌍 Translate", variant="primary")
    out_text = gr.Textbox(label="Translation", lines=5)

    def _translate(text, src, tgt):
        result = _run(bus.call("trans.text", (1,0),
            {"params": {"source_lang": src, "target_lang": tgt},
             "input": {"text": text}}))
        return result.get("output", {}).get("text", str(result))

    translate_btn.click(_translate, inputs=[src_text, src_lang, tgt_lang], outputs=[out_text])
```

---

## 🟠 P1 — High value, medium effort

### P1-1 — Apply styled HTML headers to ALL tabs
**Current state:** Only voice.py and nemotron.py have styled section headers. Ask, Chat, Mesh, etc. have plain Markdown.
**Fix:** Add a `gr.HTML(...)` styled section header at the top of each `build_*_tab()` function, matching the gradient style in `voice.py`.

### P1-2 — Rate limiting on `/bus/v1/call` and `/relay/v1/*`
**File:** `app.py` — `_mount_bus_endpoints()`
**Fix:** Wire `RateLimiter` from `hearthnet/bus/backpressure.py`
```python
from hearthnet.bus.backpressure import RateLimiter
_limiter = RateLimiter(max_calls=60, window_seconds=60)
@app.middleware("http")
async def _rate_limit(request, call_next):
    ip = request.client.host if request.client else "unknown"
    if request.url.path.startswith(("/bus/v1", "/relay/v1")):
        if not _limiter.allow(ip):
            return JSONResponse({"error": "rate_limited"}, status_code=429)
    return await call_next(request)
```

### P1-3 — Capability token expiry enforcement
**File:** `hearthnet/bus/router.py`
**Fix:** Check `token.exp < time.time()` before routing — `exp` is stored in the token but never validated.

### P1-4 — E2E encryption as default in chat (M23)
**File:** `hearthnet/services/chat/service.py`
**Status:** X3DH + Double Ratchet implemented in `hearthnet/crypto/` but `ChatService.send()` sends plaintext
**Fix:** Thread ratchet state through `ChatService._sessions` dict, encrypt payload before bus dispatch.

### P1-5 — Wire `node.start()` properly in `app.py`
**File:** `app.py`
**Currently:** `node.install_services()` called manually — skips mDNS, transport start, gossip sync
**Fix:**
```python
# Replace:
_node.install_services(corpus="community")
# With (in a thread or via asyncio.get_event_loop):
loop.run_until_complete(_node.start(corpus="community"))
```

### P1-6 — Gossip sync between nodes (X02)
**File:** `hearthnet/node.py` — add to `node.start()` after step 9
**Fix:**
```python
from hearthnet.events.sync import SyncServer
self._sync_server = SyncServer(self._event_log, self.peers)
asyncio.create_task(self._sync_server.run())
```
Enables marketplace posts and RAG documents to auto-replicate across mesh nodes.

---

## 🟡 P2 — Medium value

### P2-1 — Evidence UI tab (M30)
**Capabilities:** `evidence.claim.add`, `evidence.claim.attest`, `evidence.claim.dispute`
**Service:** `EvidenceService` — registered in research mode (`install_extended_services(research=True)`)
**File to create:** `hearthnet/ui/tabs/evidence.py`
**Add to ui/app.py** once implemented.

### P2-2 — Civil Defense UI tab (M31)
**Capabilities:** `civdef.alert.issue`, `civdef.cert.*`, `civdef.audit.chain`
**Service:** `CivilDefenseService` — registered in research mode
**File to create:** `hearthnet/ui/tabs/civdef.py`

### P2-3 — Routing trace as flow chart (U2)
**Current state:** Routing trace shown as plain text in Ask tab
**Fix:** Render as HTML/Mermaid flow diagram showing scored candidates and winner.

### P2-4 — Peer capability matrix in Mesh tab (U5)
**File:** `hearthnet/ui/tabs/mesh.py`
**Add:** Table showing each discovered peer and their capabilities.

### P2-5 — Dark mode toggle
**File:** `hearthnet/ui/app.py`
**Note:** `hearthnet/ui/theme.py` already has `emergency_theme` as a dark variant. Add a toggle.

### P2-6 — Model selection UI in Settings tab
**Current state:** Model is fixed at startup via `MODEL_ID` env var
**Fix:** Add a dropdown in Settings showing available registered backends + restart hint.

### P2-7 — Relay hub rate limiting
**File:** `hearthnet/transport/relay_hub.py`
**Fix:** Max 5 join attempts per IP per minute to prevent roster flooding.

---

## 🟢 P3 — Future / research

### P3-1 — ShardServer.forward() for distributed inference (M26)
**File:** `hearthnet/distributed_inference/shard.py:75` — `NotImplementedError`
**Requires:** torch model slicing, attention head partitioning across nodes

### P3-2 — FedLearnCoordinator.aggregate() (M28)
**File:** `hearthnet/fedlearn/coordinator.py:95` — `NotImplementedError`
**Requires:** peft, LoRA delta accumulation, secure aggregation protocol

### P3-3 — LoRa hardware serial port (M29)
**File:** `hearthnet/lora/service.py:96` — silent stub without pyserial
**Fix:** `serial.Serial("/dev/ttyUSB0", 9600)` + add `pyserial>=3.5` to requirements

### P3-4 — Browser ↔ Python mesh bridge
**Files:** `webagent/src/mesh/browsermesh.js` (PeerJS/WebRTC)
**Status:** Browser mesh and Python relay run as separate isolated meshes
**Fix:** Bidirectional WebRTC↔mailbox translation, ICE/TURN server

### P3-5 — RelayDiscovery.start() (Phase 2 peer discovery)
**File:** `hearthnet/discovery/relay.py:8` — `NotImplementedError`
**Fix:** Poll `/relay/v1/roster` on a timer, add discovered peers to `PeerRegistry`

### P3-6 — Publish to PyPI
**Command:** `python -m build && twine upload dist/*`
**Note:** `pyproject.toml` is ready

### P3-7 — Docker image publish
**File:** `Dockerfile.slim` exists
**Command:** `docker build -t hearthnet:latest . && docker push ghcr.io/ckal/hearthnet:latest`

---

## 📋 All Tasks — Status at a Glance

| Priority | Task | Status |
|----------|------|--------|
| C1–C9 | Hackathon critical items | ✅ All done |
| W1–W8 | Service/UI wiring | ✅ All done |
| P0-1 | 🖼 Image describe tab | ⏳ Open |
| P0-2 | 📄 OCR tab | ⏳ Open |
| P0-3 | 🌍 Translation tab | ⏳ Open |
| P1-1 | Styled headers on all tabs | ⏳ Open |
| P1-2 | Rate limiting on bus/relay | ⏳ Open |
| P1-3 | Token expiry enforcement | ⏳ Open |
| P1-4 | E2E encryption default | ⏳ Open |
| P1-5 | node.start() wiring | ⏳ Open |
| P1-6 | Gossip sync | ⏳ Open |
| P2-1 | Evidence UI tab | ⏳ Open |
| P2-2 | CivilDefense UI tab | ⏳ Open |
| P2-3 | Routing trace flow chart | ⏳ Open |
| P2-4 | Peer capability matrix | ⏳ Open |
| P2-5 | Dark mode toggle | ⏳ Open |
| P2-6 | Model selection UI | ⏳ Open |
| P2-7 | Relay hub rate limiting | ⏳ Open |
| P3-1 | M26 distributed inference | ⏳ Future |
| P3-2 | M28 federated learning | ⏳ Future |
| P3-3 | M29 LoRa hardware | ⏳ Future |
| P3-4 | Browser↔Python mesh bridge | ⏳ Future |
| P3-5 | RelayDiscovery.start() | ⏳ Future |
| P3-6 | PyPI publish | ⏳ Future |
| P3-7 | Docker image publish | ⏳ Future |

---

## See Also

- [`docs/ENV.md`](../ENV.md) — all environment variables, secrets, and model reference
- [`docs/SECURITY_FINDINGS.md`](../SECURITY_FINDINGS.md) — SEC-1 through SEC-8 with fixes
- [`hackathon_final_step.md`](../../hackathon_final_step.md) — project status and prize tracking
