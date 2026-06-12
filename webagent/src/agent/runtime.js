// src/agent/runtime.js
// ReAct-style agent loop. Model-agnostic: works with any `llm.chat(...)` that
// streams tokens via onToken and resolves to a string or { text }.

import { DEFAULT_SYSTEM } from "./webllm-agent.js";
import { TOOL_HELP } from "./webllm-agent.js";

export function createAgentRuntime({ llm, tools, onLog, onToken, onState }) {
  let running = false;
  let aborter = null;

  async function runTool(name, args) {
    if (!tools[name]) throw new Error(`Unknown tool: ${name}`);
    return await tools[name](args || {});
  }

  async function loop(userText, messages = [], maxIter = 8) {
    if (running) return;
    running = true;
    aborter = new AbortController();
    onState?.({ running: true });

    const chat = [
      { role: "system", content: `${DEFAULT_SYSTEM}\n\nAvailable tools:\n${TOOL_HELP}` },
      ...messages,
      { role: "user", content: userText },
    ];

    let last = "";
    try {
      for (let iter = 0; iter < maxIter; iter++) {
        onLog?.(`iter ${iter + 1}/${maxIter}`);
        last = "";
        const out = await llm.chat({
          messages: chat,
          signal: aborter.signal,
          stream: true,
          temperature: 0.4,
          max_tokens: 900,
          onToken: (t) => {
            last += t;
            onToken?.(t);
          },
        });

        const text = typeof out === "string" ? out : (out?.text || last);
        const actionMatch = text.match(/action\s*:\s*(\{[\s\S]*?\})/i);

        if (!actionMatch) {
          onState?.({ running: false, final: text });
          return text;
        }

        let action;
        try {
          action = JSON.parse(actionMatch[1]);
        } catch {
          chat.push({ role: "assistant", content: text });
          chat.push({ role: "user", content: "Observation: action JSON parse error. Re-emit valid JSON." });
          continue;
        }

        onLog?.(`tool: ${action.tool}(${JSON.stringify(stripTool(action))})`);
        let result;
        try {
          result = await runTool(action.tool, action);
        } catch (err) {
          result = `tool error: ${err?.message || err}`;
        }
        chat.push({ role: "assistant", content: text });
        chat.push({
          role: "user",
          content: `Observation from ${action.tool}: ${String(result).slice(0, 8000)}`,
        });
      }
      onState?.({ running: false, final: last });
      return last;
    } finally {
      running = false;
      aborter = null;
      onState?.({ running: false });
    }
  }

  function stop() {
    if (aborter) aborter.abort();
    running = false;
    onState?.({ running: false });
  }

  return { loop, stop, isRunning: () => running };
}

function stripTool(action) {
  const { tool, ...rest } = action;
  return rest;
}
