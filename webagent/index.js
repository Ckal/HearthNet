// index.js — browser-only wiring. No backend, no API keys.
import { mountBrowserAgent } from "./src/ui/browser-agent.js";
import { mountNewsPage } from "./src/ui/news-page.js";
import { mountMeshPanel } from "./src/ui/mesh-panel.js";
import { createWebLLM, MODELS, hasWebGPU } from "./src/llm/webllm.js";
import { scrapeUrl, webSearchNews } from "./src/news/ingest.js";
import { ragIndex, ragSearch } from "./src/rag/rag.js";

// ── model picker + progress ───────────────────────────────────────────────
const modelSel = document.getElementById("model");
const progressEl = document.getElementById("model-progress");
MODELS.forEach((m) => {
  const o = document.createElement("option");
  o.value = m.id;
  o.textContent = m.label;
  modelSel.appendChild(o);
});

if (!hasWebGPU()) {
  progressEl.textContent = "⚠ WebGPU unavailable — use Chrome/Edge to run the local model. News + mesh still work.";
  progressEl.className = "warn";
}

const webllm = createWebLLM({
  onProgress: (p) => {
    progressEl.textContent = p.text || "";
    progressEl.className = p.stage === "ready" ? "ok" : "";
  },
});

// LLM adapter the agent runtime expects, pinned to the selected model.
const llm = {
  chat: (args) => webllm.chat({ ...args, model: modelSel.value }),
};

// ── browser-local tools ─────────────────────────────────────────────────────
const deps = {
  webSearch: (q) => webSearchNews(q),
  scrape: (url) => scrapeUrl(url),
  summarize: async (text, focus) => {
    const sys = "Summarize the text concisely. " + (focus ? `Focus on: ${focus}.` : "");
    const { text: out } = await webllm.chat({
      messages: [
        { role: "system", content: sys },
        { role: "user", content: String(text).slice(0, 8000) },
      ],
      stream: false,
      model: modelSel.value,
    });
    return out;
  },
  remember: (content) => {
    const mem = JSON.parse(localStorage.getItem("hearthnet_memory") || "[]");
    mem.push({ content, ts: Date.now() });
    localStorage.setItem("hearthnet_memory", JSON.stringify(mem));
    return "saved";
  },
  schedule: (delaySec, message) => {
    const ms = Math.max(1, Number(delaySec) || 1) * 1000;
    setTimeout(() => {
      if (Notification?.permission === "granted") new Notification("HearthNet", { body: message });
      else alert(`HearthNet: ${message}`);
    }, ms);
    return `scheduled in ${Math.round(ms / 1000)}s`;
  },
  ragindex: (text, source) => ragIndex(text, source),
  ragsearch: (query, topK) => ragSearch(query, topK || 4),
};

// ── tabs ─────────────────────────────────────────────────────────────────────
const tabs = document.querySelectorAll(".tab");
const panes = document.querySelectorAll(".pane");
tabs.forEach((t) => {
  t.onclick = () => {
    tabs.forEach((x) => x.classList.remove("active"));
    panes.forEach((x) => x.classList.remove("active"));
    t.classList.add("active");
    document.getElementById(`pane-${t.dataset.tab}`).classList.add("active");
  };
});

// ── mount UIs ─────────────────────────────────────────────────────────────────
mountBrowserAgent(document.getElementById("pane-agent"), llm, deps);

let lastSignals = [];
const news = mountNewsPage(document.getElementById("pane-news"), {
  onSignals: (active) => { lastSignals = active; },
});

const meshUI = mountMeshPanel(document.getElementById("mesh-mount"), {
  onShareSignals: (signals, from) => {
    console.log("received signals from", from, signals);
  },
});

// share current active signals to the mesh
document.getElementById("share-signals").onclick = () => {
  meshUI.shareSignals(news.signals.filter((s) => s.active));
};

// ── easter egg: press "e" to toggle a global live news ticker ───────────────
let eggOn = false;
function isTyping() {
  const t = document.activeElement;
  return t && /^(input|textarea|select)$/i.test(t.tagName);
}
function escHtml(s) {
  return String(s || "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}
function populateEgg() {
  const track = document.getElementById("egg-track");
  const items = news.items || [];
  if (!items.length) {
    track.textContent = "fetching live news…";
    news.refresh().then(() => { if (eggOn) populateEgg(); });
    return;
  }
  track.innerHTML = items
    .slice(0, 40)
    .map((it) => `<span class="etk"><b>${escHtml(it.source)}</b> ${escHtml(it.title)}</span>`)
    .join('<span class="esep">•</span>');
}
document.addEventListener("keydown", (e) => {
  if (e.key.toLowerCase() !== "e" || isTyping() || e.ctrlKey || e.metaKey || e.altKey) return;
  eggOn = !eggOn;
  document.getElementById("egg-ticker").classList.toggle("hidden", !eggOn);
  if (eggOn) populateEgg();
});

// ask notification permission early (used by schedule tool)
if (typeof Notification !== "undefined" && Notification.permission === "default") {
  Notification.requestPermission().catch(() => {});
}
