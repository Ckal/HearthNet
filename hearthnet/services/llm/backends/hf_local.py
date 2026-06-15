"""Local HuggingFace Transformers backend.

Follows the OpenBMB MiniCPM demo pattern: AutoModelForCausalLM +
TextIteratorStreamer + threading.Thread instead of pipeline().

Why not pipeline():
  The transformers pipeline() abstraction can internally trigger Python pickle
  when combined with trust_remote_code=True models (their dynamically-loaded
  classes are not picklable). Using model.generate() directly with
  threading.Thread avoids any serialisation — threads share memory.

ZeroGPU note: On HF Spaces, app.py wraps _generate_sync with @spaces.GPU so
CUDA is only accessed inside the ZeroGPU-allocated window.
"""

from __future__ import annotations

import os
import threading

from hearthnet.services.llm.backends.base import BackendModel, ChatResult
from hearthnet.services.llm.tokenizers import model_family

_ON_HF_SPACE: bool = bool(os.getenv("SPACE_HOST"))


def _family(model_name: str) -> str:
    return model_family(model_name)


def _content_to_text(content) -> str:
    """Coerce a message content field to a plain string."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        return str(content.get("text") or content.get("content") or "")
    if isinstance(content, list | tuple):
        parts: list[str] = []
        for p in content:
            if isinstance(p, dict):
                parts.append(str(p.get("text") or p.get("content") or ""))
            elif isinstance(p, str):
                parts.append(p)
        return " ".join(x for x in parts if x).strip()
    return str(content)


def _trim_generated(text: str) -> str:
    """Strip role-echo / hallucinated extra turns from small-model output."""
    if not text:
        return ""
    for marker in (
        "\nuser:",
        "\nUser:",
        "\nassistant:",
        "\nAssistant:",
        "\nsystem:",
        "\nSystem:",
        "<|im_end|>",
        "<|endoftext|>",
        "<|im_start|>",
    ):
        idx = text.find(marker)
        if idx != -1:
            text = text[:idx]
    return text.strip()


class HfLocalBackend:
    name = "hf_local"

    def __init__(self, model: str = "openbmb/MiniCPM5-1B", device: str = "auto") -> None:
        self._model_name = model
        # Force CPU on HF Spaces — ZeroGPU allocates CUDA only inside @spaces.GPU
        self._device = "cpu" if _ON_HF_SPACE else device
        self._model = None
        self._tokenizer = None
        self.models = [
            BackendModel(
                name=model,
                family=_family(model),
                context_length=8192,
                requires_internet=False,
            )
        ]

    def is_available(self) -> bool:
        try:
            import transformers  # noqa: F401
            return True
        except ImportError:
            return False

    async def warm(self) -> None:
        if not self.is_available():
            return
        import asyncio
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._load)

    def _load(self) -> None:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        if self._device == "cuda" or (
            self._device == "auto" and torch.cuda.is_available()
        ):
            dtype = torch.bfloat16
            target_device = "cuda"
        else:
            dtype = torch.float32
            target_device = "cpu"

        self._tokenizer = AutoTokenizer.from_pretrained(
            self._model_name, trust_remote_code=True
        )
        self._model = AutoModelForCausalLM.from_pretrained(
            self._model_name,
            dtype=dtype,
            trust_remote_code=True,
        )
        if target_device != "cpu":
            self._model = self._model.to(target_device)

    def _generate_sync(
        self,
        messages: list[dict],
        max_tokens: int = 256,
        temperature: float = 0.7,
    ) -> str:
        """Run generation synchronously (call from a thread, not the event loop).

        Uses TextIteratorStreamer + threading.Thread following the OpenBMB demo
        pattern — model.generate() runs in a daemon thread while this thread
        drains the streamer. No pickle required.
        """
        from transformers import TextIteratorStreamer

        norm = [
            {
                "role": str(m.get("role", "user")),
                "content": _content_to_text(m.get("content")),
            }
            for m in messages
        ]

        # Prefer chat template; fall back to plain transcript
        tokenizer = self._tokenizer
        if getattr(tokenizer, "chat_template", None):
            try:
                prompt_text = tokenizer.apply_chat_template(
                    norm, tokenize=False, add_generation_prompt=True
                )
            except Exception:
                prompt_text = (
                    "\n".join(f"{m['role']}: {m['content']}" for m in norm)
                    + "\nassistant:"
                )
        else:
            prompt_text = (
                "\n".join(f"{m['role']}: {m['content']}" for m in norm)
                + "\nassistant:"
            )

        device = next(self._model.parameters()).device
        raw_inputs = tokenizer([prompt_text], return_tensors="pt")
        # token_type_ids is emitted by some tokenizers but rejected by causal LMs.
        # Use a denylist (not allowlist) so input_ids/attention_mask always pass through.
        _STRIP = {"token_type_ids"}
        model_inputs = {
            k: v.to(device)
            for k, v in raw_inputs.items()
            if k not in _STRIP
        }

        streamer = TextIteratorStreamer(
            tokenizer,
            skip_prompt=True,
            skip_special_tokens=True,
        )

        gen_kwargs: dict = dict(
            **model_inputs,
            streamer=streamer,
            max_new_tokens=max_tokens,
        )
        if temperature > 0:
            gen_kwargs.update(temperature=temperature, do_sample=True)
        else:
            gen_kwargs["do_sample"] = False

        # model.generate runs in its own thread; this thread drains the streamer
        gen_thread = threading.Thread(
            target=self._model.generate, kwargs=gen_kwargs, daemon=True
        )
        gen_thread.start()

        full_text = ""
        for token_text in streamer:
            if token_text:
                full_text += token_text

        gen_thread.join(timeout=120)
        return _trim_generated(full_text)

    async def chat(
        self,
        messages: list[dict],
        *,
        model: str = "",
        stream: bool = False,
        temperature: float = 0.7,
        max_tokens: int = 256,
        **kwargs,
    ):
        import asyncio
        import time

        if self._model is None:
            await self.warm()
        if self._model is None:
            raise RuntimeError("HF model not loaded")

        t0 = time.monotonic()
        loop = asyncio.get_running_loop()
        # Run _generate_sync in a thread — no pickling, threads share memory
        text = await loop.run_in_executor(
            None,
            lambda: self._generate_sync(
                messages, max_tokens=max_tokens, temperature=temperature
            ),
        )
        ms = int((time.monotonic() - t0) * 1000)
        return ChatResult(
            text=text,
            tokens_in=0,
            tokens_out=len(text.split()),
            model=self._model_name,
            ms=ms,
        )

    async def complete(self, prompt: str, *, model: str = "", stream: bool = False, **kwargs):
        return await self.chat(
            [{"role": "user", "content": prompt}], model=model, stream=stream, **kwargs
        )

    async def close(self) -> None:
        self._model = None
        self._tokenizer = None

    def health(self) -> dict:
        return {
            "backend": "hf_local",
            "model": self._model_name,
            "loaded": self._model is not None,
            "device": self._device,
            "on_hf_space": _ON_HF_SPACE,
        }
