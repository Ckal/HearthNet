# M04 — LLM Service

**Spec version:** v1.0
**Depends on:** M03 (bus), X04 (config), X03 (observability), backend libs (llama-cpp-python, ollama HTTP, httpx for HTTP backends)
**Depended on by:** M05 (RAG uses llm.complete internally), M08 (UI passes user queries through llm.chat)

---

## 1. Responsibility

Provide `llm.chat@1.0` and `llm.complete@1.0`. Wrap multiple inference backends (llama.cpp, Ollama, LM Studio, HF Inference API, Anthropic API, OpenAI-compatible HTTP). Register one capability instance per (backend, model, quant) tuple so the bus can see them as separate routable providers.

---

## 2. File layout

```
hearthnet/services/llm/
├── __init__.py
├── service.py                 # LlmService
├── tokenizers.py              # rough token counting per family
└── backends/
    ├── __init__.py
    ├── base.py                # LlmBackend Protocol
    ├── llama_cpp.py           # llama-cpp-python in-process
    ├── ollama.py              # Ollama HTTP at http://localhost:11434
    ├── lmstudio.py            # LM Studio HTTP (OpenAI-compatible)
    ├── hf_api.py              # HuggingFace Inference API
    └── anthropic_api.py       # Anthropic Messages API
```

---

## 3. Public API

### 3.1 `backends/base.py`

```python
# hearthnet/services/llm/backends/base.py
from dataclasses import dataclass
from typing import AsyncIterator, Protocol

@dataclass(frozen=True)
class Token:
    text:    str
    logprob: float | None
    stop:    bool

@dataclass(frozen=True)
class ChatResult:
    text:       str
    tokens_in:  int
    tokens_out: int
    stop_reason: str    # "end" | "max_tokens" | "stop_sequence" | "cancelled"
    ms:         int

@dataclass(frozen=True)
class BackendModel:
    """One model an LlmBackend can serve."""
    name:           str       # "qwen2.5-7b-instruct"
    quant:          str       # "q4_k_m", "q8_0", "fp16", "api"
    ctx_max:        int       # 8192
    modalities:     list[str] # ["text"] or ["text", "vision"]
    requires_internet: bool   # API backends → True; local → False

class LlmBackend(Protocol):
    """Abstract backend. Implementations cover one provider."""

    name:       str           # "llama_cpp" | "ollama" | ...
    models:     list[BackendModel]

    async def warm(self, model: str) -> None: ...
    async def close(self) -> None: ...

    async def chat(
        self,
        *,
        model: str,
        messages: list[dict],
        max_tokens: int = 1024,
        temperature: float = 0.7,
        top_p: float = 0.95,
        stop: list[str] | None = None,
        seed: int | None = None,
        stream: bool = True,
    ) -> AsyncIterator[Token]:
        """Yields Tokens. The final Token has stop=True."""

    async def complete(
        self,
        *,
        model: str,
        prompt: str,
        max_tokens: int = 256,
        temperature: float = 0.7,
        top_p: float = 0.95,
        stop: list[str] | None = None,
        seed: int | None = None,
        stream: bool = True,
    ) -> AsyncIterator[Token]: ...

    def count_tokens(self, model: str, text: str) -> int:
        """Approximate token count; uses a per-model tokenizer if available."""

    def max_concurrent(self, model: str) -> int:
        """Backend-specific concurrency limit. Used in capability descriptor."""

    def health(self) -> dict: ...
```

### 3.2 Concrete backends

```python
# hearthnet/services/llm/backends/llama_cpp.py
class LlamaCppBackend(LlmBackend):
    """In-process llama-cpp-python. Loads one model at a time per instance.
       Multiple LlamaCppBackend instances may coexist if VRAM allows."""

    def __init__(self, model_path: Path, model_meta: BackendModel, gpu_layers: int = -1):
        ...

# hearthnet/services/llm/backends/ollama.py
class OllamaBackend(LlmBackend):
    """HTTP-based Ollama at http://localhost:11434 (or remote)."""

    def __init__(self, base_url: str = "http://localhost:11434", models: list[str] | None = None):
        """If models is None, discover via GET /api/tags."""

# hearthnet/services/llm/backends/lmstudio.py
class LmStudioBackend(LlmBackend):
    """OpenAI-compatible HTTP at http://host:1234.
       Used in Christof's home setup at 192.168.188.25:1234."""

    def __init__(self, base_url: str, default_model: str): ...

# hearthnet/services/llm/backends/hf_api.py
class HfApiBackend(LlmBackend):
    """HuggingFace Inference API. Requires HF_TOKEN env var (declared in config.llm.backends[].api_key_env)."""

    def __init__(self, model: str, token_env: str = "HF_TOKEN"): ...

# hearthnet/services/llm/backends/anthropic_api.py
class AnthropicApiBackend(LlmBackend):
    """Anthropic Messages API. Phase 1.5; useful when internet up."""

    def __init__(self, model: str = "claude-sonnet-4-6", token_env: str = "ANTHROPIC_API_KEY"): ...
```

### 3.3 `tokenizers.py`

```python
# hearthnet/services/llm/tokenizers.py
def count_tokens_approx(model_family: str, text: str) -> int:
    """Fast heuristic: chars / 3.5 for Latin scripts, /2 for CJK.
       Used when no real tokenizer is available."""

def model_family(model_name: str) -> str:
    """'qwen2.5-7b-instruct' → 'qwen', 'llama-3-8b' → 'llama', etc."""
```

### 3.4 `service.py`

```python
# hearthnet/services/llm/service.py
class LlmService:
    name    = "llm"
    version = "1.0"

    def __init__(self, config: LlmConfig):
        self._backends: list[LlmBackend] = self._build_backends(config)

    def _build_backends(self, config: LlmConfig) -> list[LlmBackend]:
        """Instantiate each declared backend; skip backends that fail to initialise (with warning)."""

    def capabilities(self) -> list[tuple[CapabilityDescriptor, Callable, ParamsPredicate]]:
        """Emits one (descriptor, handler, predicate) per (backend, model, capability_kind) combo:
        - For each backend × each model: one llm.chat entry and one llm.complete entry.
        - Each descriptor's params include model, quant, ctx, backend."""

    async def start(self) -> None:
        """Warm one backend (the first listed) to avoid cold-start lag on first call."""

    async def stop(self) -> None: ...
    def health(self) -> dict: ...

    # --- handlers ---

    async def handle_chat(self, req: RouteRequest) -> AsyncIterator[dict]:
        """Streams SSE frames per CONTRACT §4.1.
        Picks the backend from req.body['params']['model'] (matched at routing).
        Maps backend Token → SSE 'token' frames; emits 'done' with meta."""

    async def handle_complete(self, req: RouteRequest) -> AsyncIterator[dict]:
        """Same shape as chat but for CONTRACT §4.2."""
```

### 3.5 Capability descriptors

For each `(backend, model)` pair, the service registers:

```python
# llm.chat instance
CapabilityDescriptor(
    name="llm.chat",
    version=(1, 0),
    stability="stable",
    request_schema={...},        # CONTRACT §4.1 schema
    response_schema={...},       # for non-stream fallback
    stream_schema={
        "oneOf": [
            {"type": "object", "required": ["text"], "properties": {"text": {"type": "string"}, "logprob": {"type": ["number", "null"]}}},
            {"type": "object", "required": ["tokens_out", "stop_reason", "ms"]}     # done frame
        ]
    },
    params={
        "model":   "<model.name>",
        "quant":   "<model.quant>",
        "ctx":     model.ctx_max,
        "backend": "<backend.name>",
        "modalities": model.modalities,
    },
    max_concurrent=backend.max_concurrent(model.name),
    trust_required="member",
    timeout_seconds=LLM_GENERATION_DEFAULT_TIMEOUT_SECONDS,
    idempotent=False,
)
```

### 3.6 `params_compatible` predicate

```python
def params_compatible(offered: dict, requested: dict) -> bool:
    # Required match: model.
    # Optional match: ctx (caller's must be <= offered).
    if requested.get("model") != offered.get("model"):
        return False
    if "ctx" in requested and requested["ctx"] > offered["ctx"]:
        return False
    return True
```

---

## 4. Behaviour

### 4.1 Multi-backend selection

Multiple backends may serve the same model name (e.g. llama_cpp local + LM Studio remote both offer `qwen2.5-7b-instruct`). They register as separate capability entries. The bus router picks among them by latency/load — no service-internal preference logic.

### 4.2 Streaming and cancellation

- `handle_chat` is an async generator
- Each backend `Token` becomes one SSE `token` frame
- On client disconnect, the generator is cancelled; the backend's `chat()` async iterator receives `GeneratorExit`, propagates cancellation to the underlying library (llama.cpp: set abort flag; HTTP backends: close connection)
- Cleanup must complete within 200 ms

### 4.3 Internet-dependent backends

`HfApiBackend` and `AnthropicApiBackend` set `requires_internet=True` on their `BackendModel`. The service still registers them, but the [M09](M09-emergency.md) detector triggers deregistration from the local bus when offline. On restore, they are re-registered.

### 4.4 Tool calls (Phase 2)

The `tool_call_delta` stream frame in [CONTRACT §4.1](../CAPABILITY_CONTRACT.md) is reserved. Backends that support tool calls (Anthropic, OpenAI, OpenAI-compatible) will emit these in a future version. MVP: ignored / empty.

### 4.5 Deterministic mode

If `seed` is present in request, backends that support seeded sampling apply it. `llama_cpp` does; HTTP APIs vary. When unsupported, backend still serves but does NOT promise determinism.

### 4.6 Token counting

Token counts in `meta.tokens_in` / `meta.tokens_out`:
- `llama_cpp`: exact from the model
- HTTP backends with usage in response: exact
- Others: approximate via `tokenizers.count_tokens_approx`

---

## 5. Errors

| Condition | Wire code |
|-----------|-----------|
| Unknown model | `not_found` |
| Backend HTTP 5xx | `internal_error` |
| Backend HTTP rate limit | `rate_limited` (forwarded; `retry_after_ms` if available) |
| Empty messages array | `bad_request` |
| Context exceeded | `bad_request` (with message indicating size) |
| Generation timed out | `timeout` |
| Backend crashed mid-stream | emit `error` frame, then close |

---

## 6. Configuration

From [X04 §3](../cross-cutting/X04-config.md):

```toml
[[llm.backends]]
name  = "lmstudio"
url   = "http://192.168.188.25:1234"
model = "qwen2.5-7b-instruct"

[[llm.backends]]
name  = "llama_cpp"
url   = ""                # local path; see backend
model = "qwen2.5-1.5b-instruct-q4_k_m.gguf"

[[llm.backends]]
name        = "anthropic_api"
model       = "claude-sonnet-4-6"
api_key_env = "ANTHROPIC_API_KEY"
```

Constant: `LLM_GENERATION_DEFAULT_TIMEOUT_SECONDS = 120`.

---

## 7. Tests

### Unit
- `test_capabilities_one_entry_per_model_per_backend`
- `test_handler_chat_emits_token_then_done`
- `test_handler_chat_cancellation_within_200ms`
- `test_params_compatible_model_must_match`
- `test_params_compatible_ctx_upper_bound`
- `test_internet_dependent_backend_deregistered_on_offline`

### Integration
- `test_lmstudio_backend_streams_real_tokens` (requires LM Studio at the configured address; skip otherwise)
- `test_three_node_llm_load_balance`
- `test_remote_call_through_bus_returns_full_response`

---

## 8. Cross-references

| What | Where |
|------|-------|
| `llm.chat@1.0` wire | [CONTRACT §4.1](../CAPABILITY_CONTRACT.md) |
| `llm.complete@1.0` wire | [CONTRACT §4.2](../CAPABILITY_CONTRACT.md) |
| Service protocol | [M03 §4](M03-bus.md) |
| Streaming format | [CONTRACT §5.3](../CAPABILITY_CONTRACT.md), [X01 §6](../cross-cutting/X01-transport.md) |
| Used by RAG | [M05 §5](M05-rag.md) |
| Emergency mode deregistration | [M09 §5](M09-emergency.md) |

---

## 9. Open questions

1. **Vision models** — Phase 2; reserved `modalities: ['text','vision']`. Request schema gains `messages[].content[].type='image_url'`.
2. **Tool calls** — Phase 2; reserved frame `tool_call_delta`. Will integrate Anthropic + OpenAI styles.
3. **Local model autodiscovery** — should `llama_cpp` backend scan a models directory? Useful but easy to defer.
4. **Per-model preset profiles** — Phase 2: bind a `system_prompt_template` to a model. Not yet.
