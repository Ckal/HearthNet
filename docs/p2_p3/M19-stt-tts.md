# M19 — Speech I/O (STT + TTS)

**Spec version:** v1.0 (Phase 2)
**Depends on:** M03 (bus), M07 (blobs, for audio I/O), X04 (config), X03 (observability), `openai-whisper`, `TTS` (Coqui XTTS-v2), `edge-tts` libs
**Depended on by:** M08 UI (voice query button), M22 mobile (voice notes), M18 (STT can chain into translation)

---

## 1. Responsibility

Two capabilities:

- `stt.transcribe@1.0` — audio → text, with optional translate-to-English
- `tts.synthesize@1.0` — text → audio

Two services in the same module because they share the speech domain and often pair (voice query → STT → LLM → TTS).

---

## 2. File layout

```
hearthnet/services/speech/
├── __init__.py
├── stt_service.py
├── tts_service.py
└── backends/
    ├── __init__.py
    ├── base.py            # SttBackend, TtsBackend protocols
    ├── whisper.py         # OpenAI Whisper local
    ├── whisper_remote.py  # HF inference API alternative
    ├── xtts.py            # Coqui XTTS-v2 (cloned voices)
    └── edge_tts.py        # Microsoft Edge-TTS (Christof has existing pipeline)
```

---

## 3. STT — public API

### 3.1 `backends/base.py` (STT)

```python
@dataclass(frozen=True)
class SttSegment:
    start_seconds:  float
    end_seconds:    float
    text:           str
    language:       str
    speaker:        str | None     # only if diarization enabled
    confidence:     float | None

@dataclass(frozen=True)
class SttResult:
    segments:        list[SttSegment]
    language:        str
    duration_seconds: float
    ms:              int

class SttBackend(Protocol):
    name:        str
    models:      list[str]            # "tiny" | "base" | "small" | "medium" | "large-v3"
    languages_supported: list[str]    # ISO 639-1
    supports_diarization: bool

    async def warm(self, model: str) -> None: ...
    async def close(self) -> None: ...

    async def transcribe(
        self,
        audio_bytes: bytes,
        *,
        model: str,
        language: str | None,         # "auto" handled by caller
        diarize: bool,
        translate_to_en: bool,
    ) -> AsyncIterator[SttSegment]:
        """Yields segments as they are produced. Backend may produce in big chunks
        or near-realtime depending on model + hardware."""

    def health(self) -> dict: ...
```

### 3.2 `stt_service.py`

```python
class SttService:
    name    = "stt"
    version = "1.0"

    def __init__(self, config: SpeechConfig, blob_store: BlobStore):
        ...

    def capabilities(self) -> list[tuple[CapabilityDescriptor, Callable, ParamsPredicate]]:
        """One stt.transcribe per (backend, model) combo."""

    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    def health(self) -> dict: ...

    async def handle_transcribe(self, req: RouteRequest) -> AsyncIterator[dict]:
        """CAP2 §4.11.
        1. Fetch audio blob by CID
        2. Verify duration ≤ STT_MAX_AUDIO_SECONDS
        3. Stream segments
        4. Emit done with total stats"""
```

### 3.3 Concrete STT backends

```python
class WhisperBackend(SttBackend):
    """Local Whisper via openai-whisper or faster-whisper."""

    def __init__(self, models_dir: Path, default_model: str = "large-v3", device: str = "auto"):
        ...

class WhisperRemoteBackend(SttBackend):
    """HF Inference API. requires_internet=True. Used as fallback when local Whisper not available."""

    def __init__(self, model: str = "openai/whisper-large-v3", token_env: str = "HF_TOKEN"):
        ...
```

---

## 4. TTS — public API

### 4.1 `backends/base.py` (TTS)

```python
@dataclass(frozen=True)
class TtsResult:
    audio_format:    str         # "ogg_vorbis" | "mp3" | "wav"
    sample_rate:     int         # Hz
    duration_seconds: float
    total_bytes:     int
    ms:              int

class TtsBackend(Protocol):
    name:        str
    voices:      list[str]
    languages_supported: list[str]
    formats_supported: list[str]
    cloned_voices_supported: bool

    async def warm(self, voice: str) -> None: ...
    async def close(self) -> None: ...

    async def synthesize(
        self,
        text: str,
        *,
        voice: str,
        language: str,
        speed: float,                # 0.5..2.0; 1.0 default
        output_format: str,          # "ogg_vorbis"|"mp3"|"wav"
        chunk_size_bytes: int = 16384,
    ) -> AsyncIterator[bytes]:
        """Yields raw audio chunks."""

    def health(self) -> dict: ...
```

### 4.2 `tts_service.py`

```python
class TtsService:
    name    = "tts"
    version = "1.0"

    def __init__(self, config: SpeechConfig):
        ...

    def capabilities(self) -> list[tuple[CapabilityDescriptor, Callable, ParamsPredicate]]:
        """One tts.synthesize per (backend, voice) pair (or backend-only if many voices)."""

    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    def health(self) -> dict: ...

    async def handle_synthesize(self, req: RouteRequest) -> AsyncIterator[dict]:
        """CAP2 §4.12.
        1. Validate text length ≤ TTS_MAX_TEXT_CHARS
        2. Pick backend and voice
        3. Stream chunks (base64 in 'chunk' frame)
        4. Emit done with metadata"""
```

### 4.3 Concrete TTS backends

```python
class XttsBackend(TtsBackend):
    """Coqui XTTS-v2 (Christof has the pipeline from his podcast generator).
       Supports voice cloning via reference audio."""

    def __init__(
        self,
        model: str = "tts_models/multilingual/multi-dataset/xtts_v2",
        voices_dir: Path = Path("~/.hearthnet/voices"),
        device: str = "auto",
    ):
        ...

class EdgeTtsBackend(TtsBackend):
    """Microsoft Edge-TTS — requires internet, many voices, very natural.
       Used as default when xtts is too slow on a node."""

    def __init__(self, default_voice: str = "de-DE-KatjaNeural"):
        ...
```

---

## 5. Behaviour

### 5.1 STT streaming

For long audio:
- Local Whisper produces segments incrementally (~real time on a 4090, slower on CPU)
- Service emits one SSE `segment` frame per finalised segment
- Final `done` frame includes total duration and full language detection

### 5.2 STT max length

`STT_MAX_AUDIO_SECONDS = 300`. Longer audio: caller chunks into 5-minute segments and concatenates results. Caller's responsibility to manage cross-chunk speaker continuity.

### 5.3 Voice cloning (XTTS)

`XttsBackend` supports voice cloning when given a reference audio file:

```python
config.tts.cloned_voices = [
    ClonedVoiceConfig(name="hannes_v1", reference_path=Path("~/.hearthnet/voices/hannes-3s.wav"))
]
```

Each cloned voice is registered as a separate `voice` entry in the descriptor params. Cloning happens once at startup; serves quickly thereafter.

**Privacy note:** Voice cloning is powerful and risky. Communities SHOULD policy-restrict who can register cloned voices (suggested: `trust_required="anchor"` for voice cloning). MVP allows any member; document the risk.

### 5.4 Audio format negotiation

- Input STT: any common format Whisper accepts (mp3, ogg, wav, m4a). Service normalises via `ffmpeg`.
- Output TTS: `ogg_vorbis` default (smallest), `mp3` widely-compatible, `wav` lossless.

### 5.5 Edge-TTS internet dependency

`EdgeTtsBackend` requires internet. Deregistered automatically by [M09](../../modules/M09-emergency.md) when offline. XTTS local backend continues to work.

### 5.6 STT → TTS chain (voice assistant pattern)

The voice query button in M08 UI ext:
```
mic → audio blob via M07 → stt.transcribe → text
text → llm.chat → response text
response text → tts.synthesize → audio chunks → speaker
```

This is composed at the UI layer, not internally in the speech services.

### 5.7 Christof's existing pipeline reuse

Christof has an established XTTS-v2 + Edge-TTS podcast generator pipeline. The `XttsBackend` and `EdgeTtsBackend` are designed to be drop-ins for that pipeline, sharing the same models directory.

---

## 6. Errors

| Condition | Wire code |
|-----------|-----------|
| Audio > STT_MAX_AUDIO_SECONDS | `bad_request` |
| Text > TTS_MAX_TEXT_CHARS | `bad_request` |
| Unknown voice | `not_found` |
| Audio decode failed (corrupt blob) | `bad_request` |
| Backend GPU OOM | `capacity_exceeded` |

---

## 7. Configuration

```python
config.speech.enabled              = True
config.speech.stt_backends = [
    SttBackendConfig(name="whisper", default_model="large-v3", device="auto"),
]
config.speech.tts_backends = [
    TtsBackendConfig(name="xtts", voices_dir=Path("~/.hearthnet/voices")),
    TtsBackendConfig(name="edge_tts", default_voice="de-DE-KatjaNeural"),
]
config.speech.cloned_voices = []   # list[ClonedVoiceConfig]
```

Constants: `STT_MAX_AUDIO_SECONDS`, `TTS_MAX_TEXT_CHARS`.

---

## 8. Tests

### Unit
- `test_stt_descriptor_per_model`
- `test_tts_descriptor_per_voice`
- `test_stt_max_duration_rejected`
- `test_tts_max_length_rejected`

### Integration
- `test_whisper_transcribes_de_audio` (test asset)
- `test_xtts_synthesises_then_decodes_to_correct_duration`
- `test_voice_chain_stt_llm_tts` — end-to-end
- `test_edge_tts_deregistered_when_offline`

---

## 9. Cross-references

| What | Where |
|------|-------|
| `stt.transcribe@1.0` wire | [CAP2 §4.11](../CAPABILITY_CONTRACT_v2.md) |
| `tts.synthesize@1.0` wire | [CAP2 §4.12](../CAPABILITY_CONTRACT_v2.md) |
| Voice query UI | M08 ext |
| Mobile voice notes | [M22 §4](M22-mobile-native.md) |
| Translation chain | [M18](M18-translation.md) |
| Emergency dereg for internet-bound backends | [M09 §5.2](../../modules/M09-emergency.md) |

---

## 10. Open questions

1. **Streaming STT (mic input → live caption)** — Phase 2.5. Requires WebSocket and a different backend init pattern.
2. **Real-time TTS (sub-100ms first audio)** — XTTS is 500ms+; piper-tts is fast but limited voices. Phase 3.
3. **Speaker enrollment** — explicit "this is who I am" speech sample so diarization can label by name. Phase 2.5.
4. **Audio at-rest privacy** — should voice notes be E2E? [M23](M23-e2e-encryption.md) supports it; default ON for chat attachments.
