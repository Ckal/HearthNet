// src/ui/news-page.js
// Live ticker + news feed + signal/alert panel. Browser-only, no backend.

import { RSS_SOURCES } from "../news/sources.js";
import { ingestSources } from "../news/ingest.js";
import { scoreSignals, loadAlerts, addAlert, removeAlert } from "../news/signals.js";

export function mountNewsPage(root, { onSignals } = {}) {
  let items = [];
  let signals = [];

  root.innerHTML = `
    <div class="news-ticker"><div class="news-ticker-track" data-ticker>Loading feeds…</div></div>
    <div class="news-grid">
      <div class="news-feed panel">
        <div class="panel-title">
          News feed
          <button data-refresh style="float:right">Refresh</button>
        </div>
        <div data-status class="muted" style="font-size:12px;margin-bottom:8px"></div>
        <div data-feed></div>
      </div>
      <div class="news-side">
        <div class="panel">
          <div class="panel-title">Signals</div>
          <div data-signals class="muted">—</div>
        </div>
        <div class="panel">
          <div class="panel-title">Custom alerts</div>
          <div class="row" style="margin-bottom:8px">
            <input data-alert-name placeholder="name" style="flex:0 0 90px" />
            <input data-alert-kw placeholder="keywords, comma,separated" />
            <button data-alert-add>Add</button>
          </div>
          <div data-alerts></div>
        </div>
      </div>
    </div>
  `;

  const ticker = root.querySelector("[data-ticker]");
  const feed = root.querySelector("[data-feed]");
  const statusEl = root.querySelector("[data-status]");
  const signalsEl = root.querySelector("[data-signals]");
  const alertsEl = root.querySelector("[data-alerts]");

  function renderTicker() {
    const top = items.slice(0, 25).map((it) => `<span class="tick"><b>${it.source}</b> ${esc(it.title)}</span>`);
    ticker.innerHTML = top.join("<span class='tick-sep'>•</span>") || "No items";
  }

  function renderFeed() {
    feed.innerHTML = items.slice(0, 60).map((it) => `
      <div class="news-item">
        <a href="${it.link}" target="_blank" rel="noopener">${esc(it.title)}</a>
        <div class="news-meta">${it.source} · ${it.cat || ""} ${it.published ? "· " + esc(it.published) : ""}</div>
        <div class="news-sum">${esc(it.summary || "")}</div>
      </div>
    `).join("") || "<div class='muted'>No items.</div>";
  }

  function renderSignals() {
    const active = signals.filter((s) => s.active).sort((a, b) => b.score - a.score);
    signalsEl.innerHTML = (active.length ? active : signals).map((s) => `
      <div class="signal ${s.active ? "on" : ""}">
        <span class="pill ${s.active ? "warn" : ""}">${s.name}</span>
        <span class="muted">score ${s.score}</span>
        ${s.hits?.length ? `<div class="signal-hits">${s.hits.map((h) => esc(h)).join("<br>")}</div>` : ""}
      </div>
    `).join("");
  }

  function renderAlerts() {
    const alerts = loadAlerts();
    alertsEl.innerHTML = alerts.map((a) => `
      <div class="alert-row">
        <span class="pill">${esc(a.name)}</span>
        <span class="muted">${a.keywords.map(esc).join(", ")}</span>
        <button data-del="${esc(a.name)}" style="float:right">✕</button>
      </div>
    `).join("") || "<div class='muted'>No custom alerts.</div>";
    alertsEl.querySelectorAll("[data-del]").forEach((b) => {
      b.onclick = () => {
        removeAlert(b.dataset.del);
        recomputeSignals();
        renderAlerts();
      };
    });
  }

  function recomputeSignals() {
    const extra = loadAlerts();
    signals = scoreSignals(items, extra);
    renderSignals();
    onSignals?.(signals.filter((s) => s.active));
  }

  async function refresh() {
    statusEl.textContent = "Fetching feeds…";
    let done = 0;
    try {
      items = await ingestSources(RSS_SOURCES, {
        onSource: () => {
          done += 1;
          statusEl.textContent = `Fetched ${done}/${RSS_SOURCES.length} sources…`;
        },
      });
      statusEl.textContent = `${items.length} items from ${RSS_SOURCES.length} sources`;
    } catch (err) {
      statusEl.textContent = `Feed error: ${err?.message || err}`;
    }
    renderTicker();
    renderFeed();
    recomputeSignals();
  }

  root.querySelector("[data-refresh]").onclick = refresh;
  root.querySelector("[data-alert-add]").onclick = () => {
    const n = root.querySelector("[data-alert-name]").value.trim();
    const k = root.querySelector("[data-alert-kw]").value.trim();
    if (n && k) {
      addAlert(n, k);
      root.querySelector("[data-alert-name]").value = "";
      root.querySelector("[data-alert-kw]").value = "";
      renderAlerts();
      recomputeSignals();
    }
  };

  renderAlerts();
  refresh();

  return { refresh, get items() { return items; }, get signals() { return signals; } };
}

function esc(s) {
  return String(s || "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}
