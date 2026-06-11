"""Modal deployment script for HearthNet LLM inference.

Run once to deploy a serverless GPU endpoint on Modal:

    modal deploy scripts/modal_deploy.py

Then set MODAL_ENDPOINT in your HF Space / local .env to the printed URL.

Qualifies for: Modal Best Use Of Modal prize ($10k credits).
See docs: https://modal.com/docs/guide/webhooks
"""

from __future__ import annotations

# ── Requirements ──────────────────────────────────────────────────────────────
# pip install modal transformers torch accelerate fastapi

import modal

# ── Modal app definition ──────────────────────────────────────────────────────
app = modal.App("hearthnet-llm")

MODEL_ID = "HuggingFaceTB/SmolLM2-1.7B-Instruct"

# Build a container image with the required packages
image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "transformers>=4.40",
        "torch>=2.2",
        "accelerate>=0.30",
        "fastapi",
        "uvicorn",
    )
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1"})
)


@app.cls(
    gpu="T4",
    image=image,
    container_idle_timeout=300,
    timeout=300,
)
class HearthNetLLM:
    @modal.enter()
    def load_model(self):
        from transformers import pipeline

        self.pipe = pipeline(
            "text-generation",
            model=MODEL_ID,
            device_map="auto",
            torch_dtype="auto",
        )

    @modal.web_endpoint(method="GET", label="hearthnet-llm")
    def health(self) -> dict:
        return {"status": "ok", "model": MODEL_ID}

    @modal.web_endpoint(method="POST", label="hearthnet-llm-chat")
    def chat_completions(self, request: dict) -> dict:
        """OpenAI-compatible /v1/chat/completions endpoint."""
        messages = request.get("messages", [])
        max_tokens = request.get("max_tokens", 512)
        temperature = request.get("temperature", 0.7)

        # Format messages into prompt
        prompt = ""
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                prompt += f"<|system|>\n{content}\n"
            elif role == "user":
                prompt += f"<|user|>\n{content}\n"
            elif role == "assistant":
                prompt += f"<|assistant|>\n{content}\n"
        prompt += "<|assistant|>\n"

        result = self.pipe(
            prompt,
            max_new_tokens=max_tokens,
            temperature=temperature,
            do_sample=temperature > 0,
            return_full_text=False,
        )
        text = result[0]["generated_text"]

        return {
            "id": "modal-chat-1",
            "object": "chat.completion",
            "model": MODEL_ID,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": text},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": len(prompt.split()),
                "completion_tokens": len(text.split()),
                "total_tokens": len(prompt.split()) + len(text.split()),
            },
        }


# ── Local entrypoint for testing ──────────────────────────────────────────────
@app.local_entrypoint()
def main():
    print("Deploying HearthNet LLM to Modal...")
    print(f"Model: {MODEL_ID}")
    print("After deployment, set MODAL_ENDPOINT to the printed web endpoint URL")
    print("Then add to HearthNet config.toml:")
    print()
    print("  [[llm.backends]]")
    print("  name = 'modal'")
    print("  endpoint = 'https://YOUR-ORG--hearthnet-llm-chat.modal.run'")
    print()
