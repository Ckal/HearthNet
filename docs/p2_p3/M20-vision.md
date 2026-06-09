# M20 — Vision Services

**Spec version:** v1.0 (Phase 2)
**Depends on:** M03 (bus), M07 (blobs), M04 (LLM, extended), X04 (config), X03 (observability)
**Depended on by:** M08 UI (image describe in ask tab; generate in tools), M21 tools (vision used by tool-augmented LLM), M17 OCR (Florence-2 OCR mode shared)

---

## 1. Responsibility

Two capability families:

- `img.describe@1.0` — given an image CID, produce a caption, tags, object list, or OCR
- `img.generate@1.0` — given a prompt, generate an image

Plus: extend the LLM `llm.chat@2.0` request schema with **multimodal content** (text + image_cid in messages). The multimodal path goes through M04 backends that declare `modalities: ["text", "vision"]`. M20 is responsible for providing the vision backends those LLMs depend on.

Christof's existing pipelines: Florence-2 (describe), FLUX.1-dev with LoRAs (generate), MiniCPM-V (multimodal). All wired in.

---

## 2. File layout

```
hearthnet/services/image/
├── __init__.py
├── describe_service.py
├── generate_service.py
└── backends/
    ├── __init__.py
    ├── base.py             # ImageDescribeBackend, ImageGenerateBackend
    ├── florence2.py        # Microsoft Florence-2 large
    ├── minicpm_v.py        # OpenBMB MiniCPM-V (also usable for chat-with-vision)
    ├── flux.py             # black-forest-labs FLUX.1-dev with LoRA support
    └── stable_diffusion.py # Optional SD-XL fallback
```

---

## 3. Public API — describe

### 3.1 `backends/base.py`

```python
@dataclass(frozen=True)
class ImageDescription:
    caption:    str
    detailed_caption: str | None
    tags:       list[str]
    objects:    list[dict]                  # [{label, bbox, confidence}]
    ocr_text:   str | None
    language:   str
    ms:         int

class ImageDescribeBackend(Protocol):
    name:               str
    tasks_supported:    list[str]           # subset of {"caption","detailed_caption","ocr","objects","tags"}
    languages:          list[str]
    max_pixels:         int

    async def warm(self) -> None: ...
    async def close(self) -> None: ...

    async def describe(
        self,
        image_bytes: bytes,
        *,
        task: str,
        language: str = "en",
    ) -> ImageDescription: ...

    def health(self) -> dict: ...
```

### 3.2 `describe_service.py`

```python
class ImageDescribeService:
    name    = "image.describe"
    version = "1.0"

    def __init__(self, config: VisionConfig, blob_store: BlobStore):
        ...

    def capabilities(self) -> list[tuple[CapabilityDescriptor, Callable, ParamsPredicate]]:
        """One img.describe per backend. Params include backend name and tasks_supported."""

    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    def health(self) -> dict: ...

    async def handle_describe(self, req: RouteRequest) -> dict:
        """CAP2 §4.13."""
```

### 3.3 Concrete describe backends

```python
class Florence2Backend(ImageDescribeBackend):
    def __init__(self, model: str = "microsoft/Florence-2-large", device: str = "auto"):
        ...

class MinicpmVBackend(ImageDescribeBackend):
    """Used both standalone (img.describe) and as an LLM vision backend (M04 extension)."""
    def __init__(self, model: str = "openbmb/MiniCPM-V-2_6", device: str = "auto"):
        ...
```

---

## 4. Public API — generate

### 4.1 `backends/base.py`

```python
@dataclass(frozen=True)
class GenerationResult:
    image_bytes:    bytes
    width:          int
    height:         int
    format:         str             # "png" | "webp" | "jpg"
    seed:           int
    ms:             int

class ImageGenerateBackend(Protocol):
    name:               str
    models:             list[str]
    loras_available:    list[str]
    max_resolution:     tuple[int, int]
    min_resolution:     tuple[int, int]
    supports_negative_prompt: bool

    async def warm(self, model: str) -> None: ...
    async def close(self) -> None: ...

    async def generate(
        self,
        prompt: str,
        *,
        model: str,
        lora: str | None,
        negative_prompt: str | None,
        width: int,
        height: int,
        steps: int,
        seed: int | None,
        progress_cb: Callable[[int, int], None] | None = None,
    ) -> GenerationResult: ...

    def health(self) -> dict: ...
```

### 4.2 `generate_service.py`

```python
class ImageGenerateService:
    name    = "image.generate"
    version = "1.0"

    def __init__(self, config: VisionConfig, blob_store: BlobStore):
        ...

    def capabilities(self) -> list[tuple[CapabilityDescriptor, Callable, ParamsPredicate]]:
        """One img.generate per (backend, model) combo. params declare loras_available."""

    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    def health(self) -> dict: ...

    async def handle_generate(self, req: RouteRequest) -> AsyncIterator[dict]:
        """CAP2 §4.14.
        1. Generate (streaming progress frames)
        2. Store resulting image as blob
        3. Emit done with image_cid"""
```

### 4.3 Concrete generate backends

```python
class FluxBackend(ImageGenerateBackend):
    """FLUX.1-dev with LoRA support; Christof's existing pipeline."""
    def __init__(
        self,
        model: str = "black-forest-labs/FLUX.1-dev",
        device: str = "auto",
        loras_dir: Path = Path("~/.hearthnet/loras"),
    ):
        ...

class StableDiffusionBackend(ImageGenerateBackend):
    """SD-XL fallback for nodes with smaller GPUs."""
    def __init__(self, model: str = "stabilityai/stable-diffusion-xl-base-1.0", device: str = "auto"):
        ...
```

---

## 5. Multimodal LLM extension (M04 hook)

### 5.1 Message content array

In `llm.chat@2.0` (CAP2 §4.23), each `messages[].content` may be a list:

```json
[
  {"type": "text",  "text": "Was ist auf diesem Bild?"},
  {"type": "image", "image_cid": "blake3:..."}
]
```

Backends that declare `modalities: ["text", "vision"]` in their descriptor must handle the array form. Backends that don't either:
- Are skipped by the router (params_compatible returns False when message contains image and `modalities ⊉ {"vision"}`)
- Or fall back: extract text content only, ignore images (worse UX; not recommended)

### 5.2 Vision-capable backends in M04

These M04 backends gain a `modalities: ["text","vision"]` declaration in Phase 2:

| Backend | Vision support |
|---------|----------------|
| `MinicpmVBackend` (M04 entry — same model as M20's describe) | Yes; native multimodal |
| `AnthropicApiBackend` | Yes; Claude vision via API |
| `OpenAiApiBackend` | Yes; GPT-4V |
| `Llava` (new, optional) | Yes; LLaVA via llama.cpp |
| `LlamaCppBackend` | Yes if model is multimodal (LLaVA-format) |
| `OllamaBackend` | Yes for vision models |
| Others | No |

The `M04.LlmService._build_backends` constructs these with their vision flag.

### 5.3 Image preprocessing

For LLM context, images are:
- Loaded from blob store via CID
- Resized to backend's preferred resolution (e.g. 1024×1024 for MiniCPM-V)
- Encoded base64 or sent as bytes per backend's protocol

This is opaque to the caller — the multimodal `messages` array is the contract.

---

## 6. Behaviour

### 6.1 Image describe lifecycle

```
caller → bus.call("img.describe", (1,0), {input:{image_cid:..., task:"detailed_caption"}})
  → ImageDescribeService.handle_describe
       → blob_store.read_blob_bytes(image_cid)
       → backend.describe(bytes, task=...)
       → return ImageDescription serialised
```

### 6.2 Image generate lifecycle

```
caller → bus.stream("img.generate", (1,0), {input:{prompt:"...", steps:20}})
  → ImageGenerateService.handle_generate
       → backend.generate(...) with progress_cb
       → for each step: emit 'progress' frame
       → on completion: blob_store.write_blob(image)
       → emit 'done' frame with image_cid
```

### 6.3 Safety filters

- `img.generate` prompts pass through a configurable safety filter list (regex blocklist + optional LLM-based classifier)
- Generation of identifiable persons is blocked by default (configurable: `config.vision.allow_identifiable_persons`)
- NSFW filter on output (Stable Diffusion has built-in; FLUX needs separate model)
- Failed safety → `bad_request` with `reason: "safety_filter"`

### 6.4 LoRA management

`FluxBackend.loras_available` lists LoRAs found in `loras_dir`. Caller can request a specific LoRA in `params.lora`. Loading a LoRA takes a few seconds on first use; cached thereafter.

Christof's existing LoRAs (local-style, sketches, etc.) drop into the `loras_dir`. The backend auto-discovers them.

### 6.5 GPU pressure

Vision models are heavy. Recommended:

- One Florence-2 instance per node (always-loaded)
- FLUX/SD only loaded on-demand (warm on first request, kept hot for 5 minutes)
- `max_concurrent = 1` for FLUX; `2` for describe backends

These limits are declared in the capability descriptor so the bus throttles correctly.

### 6.6 Multimodal LLM call routing

When a user sends a multimodal message:

```
UI → bus.stream("llm.chat", (2,0), {input:{messages:[{role:"user", content:[{type:"text",text:"..."},{type:"image",image_cid:"..."}]}]}})
  → Router.route filters candidates to those with modalities ⊇ {"vision"}
  → picks best (e.g. MinicpmV local, fall back to Anthropic API)
  → backend handles base64 / image-token-injection internally
```

If no vision-capable backend is online, the call returns `not_found` with a helpful `alt_capabilities` hint pointing to describe-then-text-only fallback (UI can offer this).

---

## 7. Errors

| Condition | Wire code |
|-----------|-----------|
| Unknown task | `bad_request` |
| Image too large | `bad_request` |
| Prompt safety violation | `bad_request` (reason=safety_filter) |
| LoRA not found | `not_found` |
| GPU OOM | `capacity_exceeded` |
| Backend missing for requested task | `not_implemented` |

---

## 8. Configuration

```python
config.vision.enabled                 = True
config.vision.describe_backends = [
    DescribeBackendConfig(name="florence2", model="microsoft/Florence-2-large", device="auto"),
    DescribeBackendConfig(name="minicpm_v", model="openbmb/MiniCPM-V-2_6", device="auto"),
]
config.vision.generate_backends = [
    GenerateBackendConfig(name="flux", model="black-forest-labs/FLUX.1-dev",
                          loras_dir=Path("~/.hearthnet/loras"), device="auto"),
]
config.vision.allow_identifiable_persons = False
config.vision.safety_blocklist_file       = None   # optional regex file
```

---

## 9. Tests

### Unit
- `test_describe_descriptor_per_backend`
- `test_safety_filter_blocks_known_pattern`
- `test_lora_discovery`
- `test_oom_returns_capacity_exceeded`

### Integration
- `test_florence2_caption_sample` (test image)
- `test_flux_generate_with_lora_progress_frames`
- `test_multimodal_llm_routes_to_vision_backend`
- `test_describe_then_text_fallback_when_no_vision_llm`

---

## 10. Cross-references

| What | Where |
|------|-------|
| `img.*` wire | [CAP2 §4.13–4.14](../CAPABILITY_CONTRACT_v2.md) |
| Multimodal `llm.chat@2.0` | [CAP2 §4.23](../CAPABILITY_CONTRACT_v2.md) |
| LLM service extension | M04 (extended in Phase 2 — see [00-OVERVIEW §1](../00-OVERVIEW.md)) |
| OCR overlap | [M17 §3.2 florence_ocr](M17-ocr.md) |
| Christof's pipelines | external, this is the integration |

---

## 11. Open questions

1. **Video** — Phase 3 considers `video.describe` and `video.generate` (LTX-Video). Not in Phase 2.
2. **Image editing (inpainting)** — Phase 2.5: `img.edit@1.0` capability. Reserved.
3. **Control nets (depth, edge, pose)** — Phase 2.5.
4. **3D generation** — Phase 3 with TripoSR or similar.
5. **Safety filter quality** — regex blocklist is weak. An LLM-as-judge classifier is better but adds latency. Configurable; default off.
6. **LoRA stacking** — caller specifies multiple `loras: ["...","..."]`. Implementable but adds attack surface (prompt-LoRA combos). Defer.
