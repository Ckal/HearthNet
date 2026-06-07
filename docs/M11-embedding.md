# M11 — Embedding Service

**Spec version:** v1.0
**Depends on:** M03 (bus), X04 (config), X03 (observability), `sentence-transformers`, `torch`
**Depended on by:** M05 (RAG uses embed.text), M06 (marketplace.search uses embed.text)

---

## 1. Responsibility

Provide capabilities `embed.text@1.0` (and Phase 2 `embed.image@1.0`). Wrap one or more embedding backends, register them with the bus, batch incoming requests for throughput.

Embeddings are separated from `llm.*` because their workload is different: small models, high throughput, batchable, often CPU-runnable.

---

## 2. File layout

```
hearthnet/services/embedding/
├── __init__.py
├── service.py             # EmbeddingService
└── backends.py            # SentenceTransformerBackend, OllamaEmbedBackend (Phase 2)
```

---

## 3. Public API

### 3.1 `backends.py`

```python
# hearthnet/services/embedding/backends.py
from typing import Protocol

class EmbeddingBackend(Protocol):
    name:        str      # "sentence_transformers" | "ollama" | "hf_api"
    model:       str      # "BAAI/bge-small-en-v1.5"
    dim:         int      # 384 for bge-small
    max_input:   int      # max chars per text

    async def embed(self, texts: list[str], *, normalize: bool = True) -> list[list[float]]: ...
    async def warm(self) -> None: ...
    async def close(self) -> None: ...
    def health(self) -> dict: ...


class SentenceTransformerBackend:
    """Local backend using sentence-transformers + torch."""

    def __init__(self, model: str, device: str = "auto"):
        """device: 'auto' picks cuda if available else cpu."""

    async def embed(self, texts, *, normalize=True): ...
    async def warm(self): ...
    async def close(self): ...
    def health(self): ...
```

### 3.2 `service.py`

```python
# hearthnet/services/embedding/service.py
class EmbeddingService:
    name    = "embedding"
    version = "1.0"

    def __init__(self, config: EmbeddingConfig):
        self._backend: EmbeddingBackend = SentenceTransformerBackend(
            model=config.model, device=config.device
        )

    def capabilities(self) -> list[tuple[CapabilityDescriptor, Callable, ParamsPredicate]]:
        """Returns one entry for embed.text@1.0."""

    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    def health(self) -> dict: ...

    # --- handler ---

    async def handle_embed_text(self, req: RouteRequest) -> dict:
        """Implements embed.text@1.0 (CONTRACT §4.3)."""
```

### 3.3 Capability descriptor (`embed.text@1.0`)

```python
descriptor = CapabilityDescriptor(
    name="embed.text",
    version=(1, 0),
    stability="stable",
    request_schema={
        "type": "object",
        "required": ["params", "input"],
        "properties": {
            "params": {"type": "object", "properties": {
                "model": {"type": "string"},
            }, "required": ["model"]},
            "input": {"type": "object", "required": ["texts"], "properties": {
                "texts":     {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 256},
                "normalize": {"type": "boolean", "default": True},
            }},
        },
    },
    response_schema={
        "type": "object",
        "required": ["output", "meta"],
        "properties": {
            "output": {"type": "object", "required": ["embeddings", "dim"], "properties": {
                "embeddings": {"type": "array", "items": {"type": "array", "items": {"type": "number"}}},
                "dim":        {"type": "integer"},
            }},
            "meta":   {"type": "object", "required": ["model", "ms"]},
        },
    },
    stream_schema=None,
    params={"model": "<from backend>"},
    max_concurrent=8,
    trust_required="member",
    timeout_seconds=15,
    idempotent=True,
)
```

### 3.4 `params_compatible` predicate

```python
def params_compatible(offered: dict, requested: dict) -> bool:
    # request must specify model; must match offered exactly
    return requested.get("model") == offered.get("model")
```

---

## 4. Behaviour

### 4.1 Batching (optional optimisation; Phase 1.5)

If multiple requests arrive within a small window (e.g. 20 ms), combine their `texts` arrays into one backend call. Demultiplex results back. MVP: no batching (per-request), simpler.

### 4.2 Validation

- > 256 texts → `bad_request`
- Any text > 8192 chars → `bad_request`
- Unknown model → `not_found` (model not loaded; consider asking another node)

### 4.3 Resource sizing

`max_concurrent = 8` is a sensible default on CPU. On GPU, increase via subclass that overrides `max_concurrent`. The number is declared in the manifest so the bus can throttle correctly.

---

## 5. Errors

Only the universal codes from [CONTRACT §9](../CAPABILITY_CONTRACT.md):
- `bad_request` — texts too long, too many, etc.
- `not_found` — model not loaded
- `internal_error` — backend crash

---

## 6. Configuration

From [X04 §3](../cross-cutting/X04-config.md):

```python
config.embedding.model   # "BAAI/bge-small-en-v1.5"
config.embedding.device  # "auto"
```

---

## 7. Tests

### Unit
- `test_descriptor_schema_validates_meta_schema`
- `test_handler_rejects_oversized_text`
- `test_handler_rejects_too_many_texts`
- `test_params_compatible_exact_model_match`
- `test_embed_normalises_to_unit_length`

### Integration
- `test_rag_calls_embed_via_bus` — RAG ingests, embeds via bus.call(), no direct service-to-service import
- `test_remote_embed_fallback` — local backend not loaded, bus routes to peer

---

## 8. Cross-references

| What | Where |
|------|-------|
| `embed.text@1.0` wire spec | [CONTRACT §4.3](../CAPABILITY_CONTRACT.md) |
| Service protocol | [M03 §4](M03-bus.md) |
| Consumed by RAG | [M05 §5](M05-rag.md) |
| Consumed by marketplace.search | [M06 §5](M06-marketplace.md) |

---

## 9. Open questions

1. **Phase 2 `embed.image@1.0` (CLIP)** — adds an image backend; `params` includes modality. Reserved.
2. **Batching policy** — measured trade-off; deferred. Defaults to immediate dispatch in MVP.
