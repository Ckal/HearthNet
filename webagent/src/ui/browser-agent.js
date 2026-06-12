// src/ui/browser-agent.js
import { createAgentRuntime } from "../agent/runtime.js";
import { createTools } from "../agent/tools.js";

export function mountBrowserAgent(root, llm, deps) {
  const logs = [];
  const state = { running: false, final: "" };

  const tools = createTools({
    webSearch: deps.webSearch,
    scrape: deps.scrape,
    summarize: deps.summarize,
    remember: deps.remember,
    schedule: deps.schedule,
    ragindex: deps.ragindex,
    ragsearch: deps.ragsearch,
  });

  const runtime = createAgentRuntime({
    llm,
    tools,
    onLog: (m) => {
      logs.push(m);
      render();
    },
    onToken: (t) => {
      const pre = root.querySelector("[data-answer]");
      if (pre) pre.textContent += t;
    },
    onState: (s) => {
      Object.assign(state, s);
      render();
    },
  });

  root.innerHTML = `
    <div class="agent-shell">
      <div class="agent-top">
        <input data-prompt placeholder="Ask the agent to search news, scrape pages, or monitor signals" />
        <button data-run class="primary">Run</button>
        <button data-stop>Stop</button>
      </div>
      <div class="agent-grid">
        <div class="agent-main">
          <pre data-answer></pre>
        </div>
        <div class="agent-side">
          <div class="panel">
            <div class="panel-title">Agent log</div>
            <pre data-logs></pre>
          </div>
        </div>
      </div>
    </div>
  `;

  const input = root.querySelector("[data-prompt]");
  const btnRun = root.querySelector("[data-run]");
  const btnStop = root.querySelector("[data-stop]");
  const answer = root.querySelector("[data-answer]");
  const logsEl = root.querySelector("[data-logs]");

  function render() {
    logsEl.textContent = logs.slice(-40).join("\n");
    btnRun.disabled = state.running;
    btnStop.disabled = !state.running;
  }

  async function run() {
    const q = input.value.trim();
    if (!q) return;
    answer.textContent = "";
    logs.length = 0;
    render();
    await runtime.loop(q, []);
  }

  btnRun.onclick = run;
  btnStop.onclick = () => runtime.stop();
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") run();
  });

  render();
  return runtime;
}
