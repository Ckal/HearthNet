"""M21 — Plant Identification Tool (tool.plant_identify).

Identifies plants from images using a local-first approach:

  Priority 1: bus.call("vision.describe") — Florence-2 or equivalent local vision model
              then a structured LLM parse of the description (bus.call("llm.complete"))
  Priority 2: HF Inference API (opt-in, requires HEARTHNET_HF_TOKEN env var)
  Priority 3: Returns a structured unavailable response with instructions

The service registers one capability:

  tool.plant_identify
    input:  {image_b64: str, filename: str = "", hints: list[str] = []}
    output: {
      name: str,               — latin binomial, e.g. "Urtica dioica"
      common_name: str,        — e.g. "Stinging Nettle"
      confidence: float,       — 0.0-1.0
      family: str,             — e.g. "Urticaceae"
      description: str,
      is_toxic: bool | None,
      toxicity_notes: str,
      edible_parts: list[str],
      care_tips: list[str],
      backend_used: str,       — "local_vision", "hf_api", "unavailable"
    }

ToolDefinition for use with ToolExecutor:
  from hearthnet.services.tools.plant import PLANT_TOOL_DEFINITION
"""

from __future__ import annotations

import base64
import json
import os

from hearthnet.bus.capability import CapabilityDescriptor, RouteRequest
from hearthnet.services.llm.tools import ToolDefinition

# ---------------------------------------------------------------------------
# ToolDefinition — consumed by ToolExecutor when LLM calls this tool
# ---------------------------------------------------------------------------

PLANT_TOOL_DEFINITION = ToolDefinition(
    name="plant_identify",
    description=(
        "Identify a plant from an image. "
        "Returns the plant's latin name, common name, family, edibility, toxicity, and care tips. "
        "Requires an image encoded as a base64 string."
    ),
    parameters_schema={
        "type": "object",
        "properties": {
            "image_b64": {
                "type": "string",
                "description": "Base64-encoded image (JPEG or PNG).",
            },
            "hints": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional text hints about location, season, or plant features.",
            },
        },
        "required": ["image_b64"],
    },
    bound_capability="tool.plant_identify",
    bound_version=(1, 0),
    side_effects=False,
)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class PlantIdentificationService:
    """Bus service for plant identification (M21 tool pattern).

    Attempts identification in this order:
    1. local vision.describe + llm.complete  (local-first, no internet)
    2. HF Inference API                       (opt-in: set HEARTHNET_HF_TOKEN)
    3. Structured unavailable response        (never silent failure)
    """

    name = "plant_tool"
    version = "1.0"

    def __init__(self, bus=None) -> None:
        self._bus = bus

    def capabilities(self) -> list[tuple]:
        return [
            (
                CapabilityDescriptor(
                    name="tool.plant_identify",
                    version=(1, 0),
                    stability="beta",
                    params={},
                    max_concurrent=2,
                    trust_required="member",
                    timeout_seconds=60,
                    idempotent=True,
                ),
                self.handle_identify,
                None,
            ),
        ]

    # ------------------------------------------------------------------
    # Main handler
    # ------------------------------------------------------------------

    async def handle_identify(self, req: RouteRequest) -> dict:
        inp = req.body.get("input", {})
        image_b64: str = inp.get("image_b64", "")
        hints: list[str] = inp.get("hints") or []

        if not image_b64:
            return {
                "error": "bad_request",
                "message": "image_b64 is required (base64-encoded JPEG or PNG)",
            }

        # Validate base64
        try:
            image_bytes = base64.b64decode(image_b64)
        except Exception:
            return {"error": "bad_request", "message": "image_b64 is not valid base64"}

        # Priority 1: local vision + LLM
        result = await self._try_local_vision(image_b64, hints)
        if result is not None:
            result["backend_used"] = "local_vision"
            return {"output": result, "meta": {}}

        # Priority 2: HF Inference API (opt-in)
        hf_token = os.environ.get("HEARTHNET_HF_TOKEN", "")
        if hf_token:
            result = await self._try_hf_api(image_bytes, hints, hf_token)
            if result is not None:
                result["backend_used"] = "hf_api"
                return {"output": result, "meta": {}}

        # Priority 3: unavailable
        return {
            "output": _unavailable_response(hints),
            "meta": {"backend_used": "unavailable"},
        }

    # ------------------------------------------------------------------
    # Backend: local vision.describe + llm.complete
    # ------------------------------------------------------------------

    async def _try_local_vision(
        self, image_b64: str, hints: list[str]
    ) -> dict | None:
        if self._bus is None:
            return None

        # Step 1: vision.describe
        try:
            desc_resp = await self._bus.call(
                "vision.describe",
                (1, 0),
                {
                    "input": {
                        "image_b64": image_b64,
                        "prompt": (
                            "Describe this plant in detail. "
                            "Note the leaf shape, colour, stem, flowers if visible, "
                            "and any distinguishing features."
                            + (f" Context: {', '.join(hints)}" if hints else "")
                        ),
                    }
                },
            )
        except Exception:
            return None

        description_raw = (
            desc_resp.get("output", {}).get("description", "")
            or desc_resp.get("output", "")
            or ""
        )
        if not description_raw:
            return None

        # Step 2: structured parse via LLM
        try:
            parse_prompt = _build_parse_prompt(description_raw, hints)
            llm_resp = await self._bus.call(
                "llm.complete",
                (1, 0),
                {
                    "input": {
                        "prompt": parse_prompt,
                        "max_tokens": 512,
                        "temperature": 0.0,
                    }
                },
            )
        except Exception:
            # Return partial result with just the description
            return {
                "name": "Unknown",
                "common_name": "Unknown",
                "confidence": 0.3,
                "family": "",
                "description": description_raw,
                "is_toxic": None,
                "toxicity_notes": "",
                "edible_parts": [],
                "care_tips": [],
            }

        text = (
            llm_resp.get("output", {}).get("text", "")
            or llm_resp.get("output", "")
            or ""
        )
        return _parse_llm_json(text, description_raw)

    # ------------------------------------------------------------------
    # Backend: HF Inference API
    # ------------------------------------------------------------------

    async def _try_hf_api(
        self, image_bytes: bytes, hints: list[str], token: str
    ) -> dict | None:
        """Call the public plant.id HF Space via the Inference API.

        The space used is: 'hf-vision/plant-identification' if it exists;
        otherwise falls back to a florence-2 model with a plant-specific prompt.
        Using urllib to avoid extra dependencies.
        """
        try:
            import asyncio
            import urllib.error
            import urllib.request

            loop = asyncio.get_running_loop()

            def _call() -> dict | None:
                # Build multipart request to HF Inference API
                # Model: microsoft/Florence-2-base with plant classification prompt
                url = "https://api-inference.huggingface.co/models/google/vit-base-patch16-224"
                headers = {
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/octet-stream",
                }
                req = urllib.request.Request(url, data=image_bytes, headers=headers)
                try:
                    with urllib.request.urlopen(req, timeout=30) as resp:  # nosec B310 - HF Inference API endpoint
                        raw = json.loads(resp.read().decode())
                except urllib.error.HTTPError:
                    return None

                # ViT returns list of [{label, score}]; pick top result
                if not isinstance(raw, list) or not raw:
                    return None
                top = raw[0]
                label: str = top.get("label", "")
                score: float = top.get("score", 0.0)

                # ViT ImageNet labels are not plant-specific; try to interpret
                common = label.replace("_", " ").title()
                return {
                    "name": label,
                    "common_name": common,
                    "confidence": round(score, 3),
                    "family": "",
                    "description": f"Identified by HF ViT as: {common}",
                    "is_toxic": None,
                    "toxicity_notes": "Not determined — consult a botanist before handling.",
                    "edible_parts": [],
                    "care_tips": [],
                }

            return await loop.run_in_executor(None, _call)
        except Exception:
            return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_parse_prompt(description: str, hints: list[str]) -> str:
    hints_text = (f"\nAdditional context: {', '.join(hints)}" if hints else "")
    return f"""You are a botanist. Based on this plant description, return a JSON object with these fields:
- name: latin binomial (string, e.g. "Urtica dioica") or "Unknown"
- common_name: common English name (string)
- confidence: float 0.0-1.0 based on certainty
- family: botanical family (string)
- description: one-sentence description (string)
- is_toxic: boolean or null if unknown
- toxicity_notes: safety information (string, empty if not toxic)
- edible_parts: list of edible parts (list of strings, empty if none)
- care_tips: list of 1-3 practical tips (list of strings)

Plant description:
{description}{hints_text}

Respond with ONLY the JSON object, no explanation, no markdown fences."""


def _parse_llm_json(text: str, fallback_description: str) -> dict:
    """Parse JSON from LLM response, with graceful fallback."""
    # Strip markdown fences if present
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        cleaned = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    try:
        data = json.loads(cleaned)
        return {
            "name": str(data.get("name", "Unknown")),
            "common_name": str(data.get("common_name", "")),
            "confidence": float(data.get("confidence", 0.4)),
            "family": str(data.get("family", "")),
            "description": str(data.get("description", fallback_description)),
            "is_toxic": data.get("is_toxic"),
            "toxicity_notes": str(data.get("toxicity_notes", "")),
            "edible_parts": list(data.get("edible_parts") or []),
            "care_tips": list(data.get("care_tips") or []),
        }
    except (json.JSONDecodeError, ValueError):
        return {
            "name": "Unknown",
            "common_name": "Unknown",
            "confidence": 0.3,
            "family": "",
            "description": fallback_description,
            "is_toxic": None,
            "toxicity_notes": "Could not parse identification result. Please consult a botanist.",
            "edible_parts": [],
            "care_tips": ["Take a clear photo of leaves, stem, and flowers for better accuracy."],
        }


def _unavailable_response(hints: list[str]) -> dict:
    return {
        "name": "Unavailable",
        "common_name": "Unavailable",
        "confidence": 0.0,
        "family": "",
        "description": (
            "Plant identification requires a local vision model (Florence-2 via M20) "
            "or the HEARTHNET_HF_TOKEN environment variable set for the HF Inference API."
        ),
        "is_toxic": None,
        "toxicity_notes": "Unknown — no backend available.",
        "edible_parts": [],
        "care_tips": [
            "Install a vision model: pip install transformers torch and add VisionService to your node.",
            "Or set HEARTHNET_HF_TOKEN to use the HF Inference API (requires internet).",
        ],
        "backend_used": "unavailable",
    }
