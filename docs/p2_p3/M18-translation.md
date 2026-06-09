# M18 — Translation Service

**Spec version:** v1.0 (Phase 2)
**Depends on:** M03 (bus), X04 (config), X03 (observability), `transformers`, `torch`
**Depended on by:** UI marketplace + chat (one-click translate), M19 STT (with `translate_to_en=true`)

---

## 1. Responsibility

Provide `trans.text@1.0`. Translate between languages, with strong emphasis on:
- German ↔ English (default)
- German ↔ Plattdeutsch (Niederrhein-specific, Christof's domain)
- Major European languages
- Optionally Arabic, Turkish, Russian, Ukrainian — useful in refugee-context emergencies

---

## 2. File layout

```
hearthnet/services/translation/
├── __init__.py
├── service.py
└── backends/
    ├── __init__.py
    ├── base.py
    ├── nllb.py             # facebook/nllb-200-distilled-600M
    └── plattdeutsch.py     # specialised fine-tune, optional
```

---

## 3. Public API

### 3.1 `backends/base.py`

```python
@dataclass(frozen=True)
class TranslationResult:
    text:       str
    from_lang:  str            # ISO 639-1
    to_lang:    str
    confidence: float           # 0..1 if backend supports; else 1.0 placeholder
    ms:         int

class TranslationBackend(Protocol):
    name:               str
    languages_pairs:    list[tuple[str, str]]   # supported (from, to) pairs
    max_chars:          int

    async def warm(self) -> None: ...
    async def close(self) -> None: ...

    async def translate(
        self,
        text: str,
        *,
        from_lang: str,        # "auto" supported
        to_lang: str,
        domain: str | None,
    ) -> TranslationResult: ...

    def detect_language(self, text: str) -> str | None: ...

    def health(self) -> dict: ...
```

### 3.2 Concrete backends

```python
class NllbBackend(TranslationBackend):
    """facebook/nllb-200-distilled-600M (or larger variants).
       200+ language pairs out of the box."""

    def __init__(
        self,
        model: str = "facebook/nllb-200-distilled-600M",
        device: str = "auto",
        max_chars: int = TRANSLATION_MAX_CHARS,
    ):
        ...

class PlattdeutschBackend(TranslationBackend):
    """Optional specialised fine-tune.
       If a Plattdeutsch fine-tune is present in models_dir, registers de↔nds pair.
       Otherwise no-op (the backend reports zero language pairs and is filtered out)."""

    def __init__(
        self,
        models_dir: Path,
        device: str = "auto",
    ):
        ...
```

### 3.3 `service.py`

```python
class TranslationService:
    name    = "translation"
    version = "1.0"

    def __init__(self, config: TranslationConfig):
        self._backends: list[TranslationBackend] = self._build_backends(config)

    def capabilities(self) -> list[tuple[CapabilityDescriptor, Callable, ParamsPredicate]]:
        """One trans.text entry per backend. params declare languages_pairs."""

    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    def health(self) -> dict: ...

    async def handle_translate(self, req: RouteRequest) -> dict:
        """CAP2 §4.10."""
```

### 3.4 `params_compatible` predicate

```python
def params_compatible(offered: dict, requested: dict) -> bool:
    if "backend" in requested and requested["backend"] != offered.get("backend"):
        return False
    pair = (requested.get("from"), requested.get("to"))
    if pair[0] == "auto":
        # auto-detect; backend must support at least one source → target pair
        return any(t == pair[1] for (_, t) in offered.get("languages_pairs", []))
    return pair in offered.get("languages_pairs", [])
```

---

## 4. Behaviour

### 4.1 Auto-detection

`from: "auto"`:
1. Call `detect_language(text)` (NLLB has internal language detection)
2. Substitute detected lang
3. Translate

### 4.2 Domain hints

`domain: "everyday" | "medical" | "legal" | "emergency"` is advisory. NLLB ignores it; specialised fine-tunes may use it.

### 4.3 Niederrhein focus

`PlattdeutschBackend` is Christof's local interest. When installed:

- Registers pairs `("de", "nds")` and `("nds", "de")`
- Optionally `("en", "nds")` if fine-tune extends
- Used by the marketplace UI's "auf Platt" button in [M08 settings](../../modules/M08-ui.md) ext

### 4.4 Length limits

- Single request: ≤ `TRANSLATION_MAX_CHARS` (4000)
- For longer texts, callers chunk by paragraph and recombine

### 4.5 Batching

Internal: requests within 100 ms batched up to 8 strings per forward pass. Improves GPU utilisation. Demultiplexed back. Transparent to callers.

### 4.6 Caching

In-memory LRU cache `(text_hash, from, to) → result`, max 10k entries. Big wins for marketplace UI which re-translates same posts on every refresh.

---

## 5. Errors

| Condition | Wire code |
|-----------|-----------|
| Pair not supported by any backend | `not_found` |
| Text too long | `bad_request` |
| Detection failed | `bad_request` |
| Backend OOM | `capacity_exceeded` |

---

## 6. Configuration

```python
config.translation.enabled       = True
config.translation.backends = [
    TranslationBackendConfig(name="nllb", model="facebook/nllb-200-distilled-600M", device="auto"),
    TranslationBackendConfig(name="plattdeutsch", models_dir=Path("~/.hearthnet/models/plattdeutsch")),
]
```

Constants: `TRANSLATION_MAX_CHARS`.

---

## 7. Tests

### Unit
- `test_descriptor_schema_validates`
- `test_params_compatible_pair_must_match`
- `test_auto_detect_substitutes_source_lang`
- `test_text_too_long_rejected`
- `test_cache_hit_returns_immediately`

### Integration
- `test_german_to_english_quality` (BLEU above floor)
- `test_plattdeutsch_pair_registered_when_finetune_present`
- `test_marketplace_one_click_translate_end_to_end`

---

## 8. Cross-references

| What | Where |
|------|-------|
| `trans.text@1.0` wire | [CAP2 §4.10](../CAPABILITY_CONTRACT_v2.md) |
| STT translate-to-EN feature | [M19 §4.3](M19-stt-tts.md) |
| Marketplace one-click | [M08 ext](../../modules/M08-ui.md) |
| Niederrhein context | Christof's domain |

---

## 9. Open questions

1. **Fine-tune in-the-loop.** A community could fine-tune the Plattdeutsch model on its own corpus over time. Reserved.
2. **Document-level translation.** Currently per-string. Document-coherence translation (better than chunked) is Phase 3.
3. **Glossary support.** Domain glossaries (technical terms, names) preserved across translation. Phase 2.5.
