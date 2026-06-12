// src/llm/webllm.js
// Browser-local LLM via @mlc-ai/web-llm (WebGPU). No server, no API keys.
// Models are downloaded once and cached in the browser (IndexedDB / Cache API).

import * as webllm from "https://esm.run/@mlc-ai/web-llm";

// Small, browser-friendly instruct models. First is the default.
export const MODELS = [
  { id: "SmolLM2-360M-Instruct-q4f16_1-MLC", label: "SmolLM2 360M (smallest, fastest)" },
  { id: "Qwen2.5-0.5B-Instruct-q4f16_1-MLC", label: "Qwen2.5 0.5B" },
  { id: "Llama-3.2-1B-Instruct-q4f32_1-MLC", label: "Llama 3.2 1B (best quality)" },
];

export function hasWebGPU() {
  return typeof navigator !== "undefined" && "gpu" in navigator;
}

export function createWebLLM({ onProgress } = {}) {
  let engine = null;
  let currentModel = null;
  let loading = null;

  async function ensure(modelId) {
    const id = modelId || MODELS[0].id;
    if (engine && currentModel === id) return engine;
    if (loading) await loading.catch(() => {});

    if (!hasWebGPU()) {
      throw new Error(
        "WebGPU is not available in this browser. Use a recent Chrome/Edge (or enable WebGPU) to run the local model."
      );
    }

    loading = (async () => {
      onProgress?.({ stage: "init", model: id, text: `Loading ${id}…` });
      engine = await webllm.CreateMLCEngine(id, {
        initProgressCallback: (p) => onProgress?.({ stage: "download", model: id, text: p.text, progress: p.progress }),
      });
      currentModel = id;
      onProgress?.({ stage: "ready", model: id, text: `Model ready: ${id}` });
      return engine;
    })();

    return loading;
  }

  // Matches the runtime contract: chat({ messages, stream, onToken, temperature, max_tokens, signal }).
  async function chat({ messages, stream = true, onToken, temperature = 0.4, max_tokens = 900, model, signal }) {
    const eng = await ensure(model);
    let text = "";

    if (stream) {
      const reply = await eng.chat.completions.create({
        messages,
        temperature,
        max_tokens,
        stream: true,
      });
      for await (const chunk of reply) {
        if (signal?.aborted) break;
        const delta = chunk.choices?.[0]?.delta?.content || "";
        if (delta) {
          text += delta;
          onToken?.(delta);
        }
      }
      return { text };
    }

    const res = await eng.chat.completions.create({ messages, temperature, max_tokens, stream: false });
    text = res.choices?.[0]?.message?.content || "";
    return { text };
  }

  async function complete(prompt, opts = {}) {
    const { text } = await chat({ messages: [{ role: "user", content: prompt }], stream: false, ...opts });
    return text;
  }

  return { chat, complete, ensure, get model() { return currentModel; } };
}
