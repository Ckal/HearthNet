"""HearthNet — Hugging Face Space entry point.

This Space runs a **real** HearthNet node using HuggingFace Transformers as the
LLM backend. All 7 tabs are live:

  Ask        — LLM + RAG queries routed via capability bus
  Chat       — Event-sourced direct messages between nodes
  Mesh       — Live topology graph of discovered peers
  Marketplace — Community offers / requests / emergency posts
  Files      — BLAKE3 content-addressed blob store
  Emergency  — Offline-mode probe and connectivity status
  Settings   — Node identity, peer list, QR invite, RAG ingest

Difference between this Space and a local install
──────────────────────────────────────────────────
  HF Space     → single node, no real peer mesh, SmolLM2-135M for LLM
  Local node   → full peer mesh, any LLM backend (Ollama / llama.cpp / HF),
                 file sharing, multi-node chat, hardware acceleration

Quick start (local, full features):
  git clone https://huggingface.co/spaces/build-small-hackathon/HearthNet
  cd HearthNet
  pip install -e .
  python -m hearthnet.cli run
  # Open http://localhost:7860 in your browser

See docs/HOWTO.md for Raspberry Pi, Docker, and multi-node mesh setup.
"""
from __future__ import annotations

import os

import gradio as gr

# ─────────────────────────────────────────────────────────────────────────────
# Optional HF Spaces GPU decorator
# ─────────────────────────────────────────────────────────────────────────────
try:
    import spaces as _spaces  # type: ignore[import]
    HF_SPACES = True
except ImportError:
    HF_SPACES = False

# ─────────────────────────────────────────────────────────────────────────────
# Bootstrap a real HearthNet node
# ─────────────────────────────────────────────────────────────────────────────

MODEL_ID = os.getenv("MODEL_ID", "HuggingFaceTB/SmolLM2-135M-Instruct")
MODEL_REVISION = os.getenv("MODEL_REVISION", "12fd25f77366fa6b3b4b768ec3050bf629380bac")

SEED_CORPUS = [
    {
        "id": "water.001",
        "title": "Water Safety",
        "text": (
            "If the mains supply is disrupted, use stored clean water first. "
            "Rainwater should be filtered through clean cloth, brought to a rolling "
            "boil for at least one minute, and stored in a clean covered container."
        ),
    },
    {
        "id": "power.001",
        "title": "Power Outage",
        "text": (
            "Keep refrigerators closed. Disconnect sensitive devices. Reserve battery "
            "banks for communication. Share verified charging points through the local "
            "marketplace."
        ),
    },
    {
        "id": "mesh.001",
        "title": "HearthNet Routing",
        "text": (
            "A HearthNet UI sends requests to a capability bus. The bus scores local "
            "capabilities higher than remote ones and routes to the best available "
            "provider. If a node is quarantined the bus fails over automatically."
        ),
    },
    {
        "id": "firstaid.001",
        "title": "First Aid Basics",
        "text": (
            "Check scene safety first. Call local emergency contacts when available. "
            "Assess breathing. Control severe bleeding with direct pressure. Keep the "
            "person warm until help arrives."
        ),
    },
    {
        "id": "setup.001",
        "title": "Node Setup",
        "text": (
            "Install HearthNet with pip install hearthnet. Run python -m hearthnet.cli run "
            "to start a node. Other devices on the same LAN discover it automatically via "
            "mDNS. Use the Settings > Join This Mesh section to generate an invite QR code "
            "for devices on different networks."
        ),
    },
]


def _build_node():
    """Bootstrap the HearthNet node for this Space.

    Uses HfLocalBackend (SmolLM2-135M) so inference works without Ollama.
    Falls back to _UnavailableBackend if transformers is not installed.
    """
    from hearthnet.node import HearthNode
    from hearthnet.services.llm.service import LlmService
    from hearthnet.services.llm.backends.hf_local import HfLocalBackend
    from hearthnet.services.marketplace.service import MarketplaceService
    from hearthnet.services.chat.service import ChatService
    from hearthnet.services.demo import RagService as DemoRagService

    node = HearthNode(
        node_id="hf-space",
        display_name="HearthNet Space",
        community_id="ed25519:hf-space-demo",
    )

    # LLM — HF Transformers backend (SmolLM2 by default)
    try:
        backend = HfLocalBackend(model=MODEL_ID)
        # On ZeroGPU Spaces, patch the backend to use the @spaces.GPU wrapper so
        # GPU memory is properly allocated per inference call.
        if HF_SPACES:
            import asyncio
            import time as _time
            from hearthnet.services.llm.backends.base import ChatResult

            @_spaces.GPU(duration=120)
            def _gpu_pipeline_call(pipeline, prompt: str, max_new_tokens: int, temperature: float) -> list:
                """GPU-wrapped pipeline call. ZeroGPU allocates GPU for this function."""
                return pipeline(
                    prompt,
                    max_new_tokens=max_new_tokens,
                    temperature=temperature,
                    do_sample=True,
                    return_full_text=False,
                )

            # Store the GPU wrapper on the backend so it can be replaced without
            # changing the public API.
            backend._gpu_pipeline_call = _gpu_pipeline_call  # type: ignore[attr-defined]

            async def _patched_chat(
                self,
                messages: list[dict],
                *,
                model: str = "",
                stream: bool = False,
                temperature: float = 0.7,
                max_tokens: int = 256,
                **kwargs,
            ):
                if self._pipeline is None:
                    await self.warm()
                if self._pipeline is None:
                    raise RuntimeError("HF model not loaded")
                t0 = _time.monotonic()
                prompt = (
                    "\n".join(f"{m['role']}: {m['content']}" for m in messages)
                    + "\nassistant:"
                )
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None,
                    lambda: self._gpu_pipeline_call(self._pipeline, prompt, max_tokens, temperature),
                )
                text = result[0]["generated_text"] if result else ""
                ms = int((_time.monotonic() - t0) * 1000)
                return ChatResult(
                    text=text,
                    tokens_in=len(prompt.split()),
                    tokens_out=len(text.split()),
                    model=self._model_name,
                    ms=ms,
                )

            HfLocalBackend.chat = _patched_chat  # type: ignore[method-assign]

        llm = LlmService(backends=[backend])
    except Exception:
        llm = LlmService()  # _UnavailableBackend — shows clear error

    node.bus.register_service(llm)

    # RAG — pre-seeded community corpus using demo RagService (in-memory)
    from hearthnet.services.demo import RagService as DemoRagService
    rag = DemoRagService(corpus="community")
    rag.documents = list(SEED_CORPUS)
    node.bus.register_service(rag)

    # Marketplace, Chat, Files
    node.bus.register_service(MarketplaceService())
    node.bus.register_service(ChatService(node.node_id))

    # File blobs (in-memory for Space; persisted to disk on local install)
    try:
        from hearthnet.services.files.service import FileService
        node.bus.register_service(FileService())
    except Exception:
        pass

    return node


# Build node and Gradio app at import time (HF Spaces requires module-level `demo`)
_node = _build_node()

from hearthnet.ui.app import build_ui as _build_ui  # noqa: E402

_ui = _build_ui(
    bus=_node.bus,
    state_bus=_node.state_bus,
    display_name=_node.display_name,
    node_id=_node.node_id,
    community_id=_node.community_id,
)
demo = _ui.build()

if __name__ == "__main__":
    demo.launch()
