# M17 — OCR Service

**Spec version:** v1.0 (Phase 2)
**Depends on:** M03 (bus), M07 (blobs, for reading image/PDF inputs and storing extracted text), M11 (embedding, when integrating with M05 RAG), X04 (config), X03 (observability)
**Depended on by:** M05 RAG (ingest of scanned PDFs), M20 vision (img.describe can fall back to OCR for text-heavy images)

---

## 1. Responsibility

Provide `ocr.image@1.0` and `ocr.pdf@1.0`. Wrap several OCR backends so the bus can route between them by document type and language. Specifically engineered to handle:

- Modern German printed text (Tesseract)
- Handwriting (TrOCR / Microsoft Florence-OCR)
- Historical scripts — Sütterlin, Kurrent, Latin, Arabic, Cyrillic (Christof's multilingual harness)
- Mixed-language documents (auto-detection)

---

## 2. File layout

```
hearthnet/services/ocr/
├── __init__.py
├── service.py            # OcrService
└── backends/
    ├── __init__.py
    ├── base.py           # OcrBackend Protocol
    ├── tesseract.py      # Tesseract via pytesseract
    ├── trocr.py          # Microsoft TrOCR via transformers
    ├── multilingual.py   # Christof's self-improving harness (CHURRO, olmOCR-2)
    └── florence_ocr.py   # Florence-2 OCR mode (overlap with M20)
```

---

## 3. Public API

### 3.1 `backends/base.py`

```python
# hearthnet/services/ocr/backends/base.py
from dataclasses import dataclass

@dataclass(frozen=True)
class OcrBlock:
    text:        str
    bbox:        tuple[int, int, int, int]   # (x, y, w, h) in pixel coords
    confidence:  float                       # 0..1
    language:    str | None

@dataclass(frozen=True)
class OcrPageResult:
    page:             int                    # 1-indexed
    text:             str                    # concatenated, reading order
    blocks:           list[OcrBlock]
    languages:        list[str]              # detected, ordered by prevalence
    confidence_mean:  float
    ms:               int

class OcrBackend(Protocol):
    name:               str       # "tesseract" | "trocr" | "multilingual" | "florence_ocr"
    languages_supported: list[str] # ISO 639-2 codes: "deu","eng","lat","ara","rus", ...
    supports_handwriting: bool
    max_image_pixels:   int

    async def warm(self) -> None: ...
    async def close(self) -> None: ...

    async def ocr_image(
        self,
        image_bytes: bytes,
        *,
        languages: list[str] | None,        # None → auto-detect
        preprocess: dict | None = None,     # {deskew, denoise, dpi}
    ) -> OcrPageResult: ...

    async def ocr_pdf_page(
        self,
        pdf_bytes: bytes,
        *,
        page: int,
        languages: list[str] | None,
        preprocess: dict | None = None,
    ) -> OcrPageResult: ...

    def health(self) -> dict: ...
```

### 3.2 Concrete backends

| File | Class | Notes |
|------|-------|-------|
| `backends/tesseract.py` | `TesseractBackend(min_confidence: float = 0.5)` | Languages: any installed traineddata. Subprocess via pytesseract. |
| `backends/trocr.py` | `TrocrBackend(model: str = "microsoft/trocr-large-handwritten", device: str = "auto")` | Handwriting; CUDA preferred. |
| `backends/multilingual.py` | `MultilingualHarnessBackend(model: str = "self-improving-ocr-v1", device: str = "auto", harness_dir: Path)` | Christof's harness (CHURRO, olmOCR-2, retrieval-augmented correction, Kurrent/Sütterlin/Latin/Arabic/Cyrillic). Configured via `harness_dir`. |
| `backends/florence_ocr.py` | `FlorenceOcrBackend(model: str = "microsoft/Florence-2-large")` | Reuses M20 vision backend in OCR mode. |

`MultilingualHarnessBackend` is the headline integration for Christof's existing work. It exposes the same `OcrBackend` interface and lets the harness's internal page-level VLMs do the heavy lifting.

### 3.3 `service.py`

```python
# hearthnet/services/ocr/service.py
class OcrService:
    name    = "ocr"
    version = "1.0"

    def __init__(self, config: OcrConfig, blob_store: BlobStore, event_log: EventLog):
        self._backends: dict[str, OcrBackend] = self._build_backends(config)

    def capabilities(self) -> list[tuple[CapabilityDescriptor, Callable, ParamsPredicate]]:
        """One ocr.image entry per backend; one ocr.pdf entry per backend.
        params include backend name and supported languages."""

    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    def health(self) -> dict: ...

    # --- handlers ---

    async def handle_image(self, req: RouteRequest) -> dict:
        """CAP2 §4.8.
        1. Resolve image_cid via blob_store
        2. Pick backend from params.backend
        3. Run; build response"""

    async def handle_pdf(self, req: RouteRequest) -> AsyncIterator[dict]:
        """CAP2 §4.9.
        1. Resolve doc_cid
        2. For each page in page_range:
           emit 'progress' frame
           emit 'page' frame
        3. If store_text:true, write concatenated text as new blob; emit done with text_cid"""
```

### 3.4 `params_compatible` predicate

```python
def params_compatible(offered: dict, requested: dict) -> bool:
    # backend must match if specified
    if "backend" in requested and requested["backend"] != offered.get("backend"):
        return False
    # all requested languages must be supported by this backend
    requested_langs = set(requested.get("languages", []))
    offered_langs   = set(offered.get("languages_supported", []))
    return requested_langs.issubset(offered_langs)
```

---

## 4. Behaviour

### 4.1 Auto-language detection

If `languages` is omitted or set to `["auto"]`:

1. Sample 3 random pages
2. Run lightweight script detection (Tesseract `osd`)
3. Choose top 2 scripts
4. Re-run with that language set

Backends that don't support `osd` fall back to a fixed default (configured per backend).

### 4.2 Preprocessing pipeline

`preprocess` dict supports:
- `deskew: bool` — straighten image
- `denoise: bool` — bilateral filter
- `binarize: bool` — Otsu threshold
- `dpi: int` — target resolution; upscale if lower
- `contrast_normalise: bool`

Default: `{"deskew": true, "denoise": false}`. Heavy preprocessing slows ingest meaningfully; only enable per document.

### 4.3 Quality estimation

Each page result reports `confidence_mean`. Below 0.6, the service emits a `low_quality` warning frame and recommends:
- Trying a different backend (e.g. switch from Tesseract to multilingual harness for historic text)
- Raising DPI
- Re-scanning

### 4.4 Integration with RAG

[M05 §10 open question 4](../../modules/M05-rag.md) is now answered:

```
RagService.handle_ingest receives a scanned PDF (mime_type=image/scanned-pdf or detected)
  → bus.call("ocr.pdf", (1,0), {input:{doc_cid:..., store_text:true}})
  → receive text_cid
  → ingest the text_cid blob (which is now extracted plaintext) as normal
  → emit rag.document.ingested event (with metadata noting ocr_backend used)
```

The OCR text is stored as a separate blob, content-addressed. Re-ingestion is idempotent.

### 4.5 Page-range and parallelism

`page_range: [1, 50]` lets callers process partial documents. Pages are OCR'd serially within one call. For very large PDFs, callers should split into ranges and call concurrently — the bus enforces per-capability concurrency.

`OCR_MAX_PAGES_PER_REQUEST = 50` is the hard ceiling per call.

### 4.6 PDF text-layer detection

Before OCR'ing, the service checks if the PDF has an extractable text layer (via `pypdf`). If yes and confidence is decent (heuristic), it returns the text-layer content directly — much cheaper than OCR. Caller can force OCR with `force_ocr: true`.

### 4.7 Christof's multilingual harness integration

The `MultilingualHarnessBackend` wraps Christof's existing self-improving OCR pipeline:

- Internal models: CHURRO (page-level VLM), olmOCR-2 (page-level VLM)
- Retrieval-augmented correction over a script-specific corpus
- Kurrent + Sütterlin support for German historical documents
- Latin / Arabic / Cyrillic script recognition

Configuration:

```python
config.ocr.multilingual_harness_dir = Path("/srv/ocr-harness")
config.ocr.multilingual_max_pages_concurrent = 2
```

The harness is GPU-intensive. On CPU-only nodes, it deregisters itself at startup.

---

## 5. Storage and lifecycle

- Input image/PDF: fetched from blob store via CID
- Output text: optionally stored as a new blob (`store_text: true`)
- Side-effect: `ocr.document.indexed` event in the community log (carries text_cid for downstream replication)

OCR backends do NOT cache results inside themselves. Reuse comes from caching at the RAG/blob layer (same `doc_cid` → already-extracted-text blob).

---

## 6. Errors

| Condition | Wire code |
|-----------|-----------|
| Unknown backend | `not_found` |
| Languages not supported by any backend | `bad_request` |
| Image too large (> max_image_pixels) | `bad_request` |
| Page-range exceeds document | `bad_request` |
| > OCR_MAX_PAGES_PER_REQUEST | `bad_request` |
| Backend crash | `internal_error` |
| GPU OOM on multilingual | `capacity_exceeded` (with retry_after) |

---

## 7. Configuration

```python
config.ocr.enabled                 = True
config.ocr.backends = [
    OcrBackendConfig(name="tesseract", languages=["deu","eng","fra","lat"]),
    OcrBackendConfig(name="trocr", model="microsoft/trocr-large-handwritten"),
    OcrBackendConfig(name="multilingual", harness_dir=Path("/srv/ocr-harness")),
]
config.ocr.default_dpi             = OCR_DEFAULT_DPI    # 300
config.ocr.max_pages_per_request   = OCR_MAX_PAGES_PER_REQUEST
config.ocr.text_layer_first        = True
```

Constants: `OCR_DEFAULT_DPI`, `OCR_MAX_PAGES_PER_REQUEST`.

---

## 8. Tests

### Unit
- `test_descriptor_schema_validates_meta_schema`
- `test_params_compatible_language_subset`
- `test_text_layer_short_circuits_when_present`
- `test_force_ocr_bypasses_text_layer`
- `test_low_quality_emits_warning_frame`

### Integration
- `test_tesseract_german_print` (with a known sample)
- `test_trocr_handwriting_sample`
- `test_multilingual_kurrent_sample` (if harness installed)
- `test_rag_ingest_scanned_pdf_end_to_end`
- `test_ocr_pdf_progress_frames`

---

## 9. Cross-references

| What | Where |
|------|-------|
| `ocr.*` wire | [CAP2 §4.8–4.9](../CAPABILITY_CONTRACT_v2.md) |
| Blob store dependency | [M07 §3](../../modules/M07-file-blobs.md) |
| RAG integration | [M05 §10 q4](../../modules/M05-rag.md) — now resolved |
| Vision overlap (Florence-2 OCR mode) | [M20 §4.3](M20-vision.md) |
| `ocr.document.indexed` event | [CAP2 §7.1](../CAPABILITY_CONTRACT_v2.md) |
| Christof's harness | external project; this module is the integration surface |

---

## 10. Open questions

1. **Multilingual harness auto-update.** The harness self-improves; should the model versions be event-logged so we can replay deterministically? Yes — record the harness version hash in each `ocr.document.indexed` event.
2. **Manuscript-quality preprocessing.** Some historic documents need bespoke preprocessing (e.g. ink-bleed removal). Phase 2.5 might add a `preprocess_profile` enum.
3. **Reading order from layout.** Currently we trust the backend's reading order. For multi-column documents, an explicit layout model (LayoutLMv3) might help. Phase 3.
4. **Streaming OCR for very large images.** Currently atomic. Could tile and stream. Defer.
