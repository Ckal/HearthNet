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
            "boil for at least one minute, and stored in a clean covered container. "
            "Adult daily minimum: 3 litres for drinking and sanitation."
        ),
    },
    {
        "id": "power.001",
        "title": "Power Outage",
        "text": (
            "Keep refrigerators closed to preserve food up to 4 hours. "
            "Disconnect sensitive electronics. Reserve battery banks for communication. "
            "Share verified charging points through the local marketplace. "
            "Candles are a fire risk — use battery or wind-up torches."
        ),
    },
    {
        "id": "mesh.001",
        "title": "HearthNet Routing",
        "text": (
            "A HearthNet UI sends requests to a capability bus. The bus scores local "
            "capabilities higher than remote ones and routes to the best available "
            "provider. If a node is quarantined the bus fails over automatically. "
            "RAG corpus routing uses the 'corpus' parameter to match the right node."
        ),
    },
    {
        "id": "firstaid.001",
        "title": "First Aid — Bleeding",
        "text": (
            "Apply direct firm pressure to the wound with a clean cloth. "
            "Maintain pressure for at least 10 minutes. Do not remove the cloth — "
            "add more on top if it soaks through. Elevate the limb above heart level "
            "if possible. Seek emergency care if bleeding is severe or arterial."
        ),
    },
    {
        "id": "firstaid.002",
        "title": "CPR Basics",
        "text": (
            "If a person is unresponsive and not breathing normally: call emergency services, "
            "then give 30 chest compressions (hard, fast, centre of chest) followed by "
            "2 rescue breaths. Continue the 30:2 cycle until help arrives or the person "
            "recovers. Hands-only CPR (compressions without rescue breaths) is acceptable "
            "for untrained bystanders."
        ),
    },
    {
        "id": "setup.001",
        "title": "Node Setup — Quick Start",
        "text": (
            "Install HearthNet with: pip install hearthnet. "
            "Run: python -m hearthnet.cli run "
            "to start a node. Open http://localhost:7860 in your browser. "
            "Other devices on the same LAN discover your node automatically via mDNS. "
            "Use the Settings tab to generate an invite QR for devices on other networks."
        ),
    },
    {
        "id": "setup.002",
        "title": "Node Setup — Specialized Nodes",
        "text": (
            "Register only the capabilities your hardware supports. "
            "An OCR Raspberry Pi: register OcrService. "
            "A medical knowledge node: register RagService with a medical corpus. "
            "A thin client (phone): register no services — all bus calls route to peers. "
            "The bus auto-discovers and routes to the best provider in the mesh."
        ),
    },
    {
        "id": "emergency.001",
        "title": "Emergency Communication Plan",
        "text": (
            "Before a disaster: exchange node IDs with neighbours. "
            "During internet outage: HearthNet switches to offline mode automatically. "
            "All routing stays local. Use the mesh to share offers and requests. "
            "For emergency alerts, post to the Marketplace with category=emergency. "
            "Battery-powered device with HearthNet can serve the whole neighbourhood."
        ),
    },
    {
        "id": "food.001",
        "title": "Emergency Food Safety",
        "text": (
            "In a power outage, refrigerated food is safe for up to 4 hours. "
            "Frozen food stays safe for 24-48 hours if the freezer stays closed. "
            "Discard meat, poultry, seafood, dairy, or cooked food left above 4°C "
            "for more than 2 hours. When in doubt, throw it out."
        ),
    },
    {
        "id": "shelter.001",
        "title": "Shelter in Place",
        "text": (
            "During chemical or biological hazards, stay indoors. "
            "Close all windows and doors. Turn off HVAC. "
            "Seal gaps with wet towels or tape. "
            "Monitor emergency broadcasts on battery radio. "
            "Do not leave until authorities give the all-clear."
        ),
    },
]


def _build_node():
    """Bootstrap the HearthNet node for this Space.

    Uses HfLocalBackend (SmolLM2-135M) so inference works without Ollama.
    Falls back to _UnavailableBackend if transformers is not installed.
    """
    from hearthnet.node import HearthNode
    from hearthnet.services.chat.service import ChatService
    from hearthnet.services.demo import RagService as DemoRagService
    from hearthnet.services.files.service import FileService
    from hearthnet.services.llm.backends.hf_local import HfLocalBackend
    from hearthnet.services.llm.service import LlmService
    from hearthnet.services.marketplace.service import MarketplaceService

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
            def _gpu_pipeline_call(
                pipeline, prompt: str, max_new_tokens: int, temperature: float
            ) -> list:
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
                    "\n".join(f"{m['role']}: {m['content']}" for m in messages) + "\nassistant:"
                )
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None,
                    lambda: self._gpu_pipeline_call(
                        self._pipeline, prompt, max_tokens, temperature
                    ),
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
    rag = DemoRagService(corpus="community")
    rag.documents = list(SEED_CORPUS)
    node.bus.register_service(rag)

    # Marketplace, Chat, Files
    node.bus.register_service(MarketplaceService())
    node.bus.register_service(ChatService(node.node_id))
    node.bus.register_service(FileService())

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
