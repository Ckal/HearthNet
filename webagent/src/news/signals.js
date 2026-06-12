// src/news/signals.js
// Keyword-based signal scoring. Signals are ALERTS, not assertions of fact.

export const SIGNALS = [
  { name: "war", keywords: ["airstrike", "mobilization", "missile", "ceasefire", "front line", "shelling", "invasion"] },
  { name: "cyber", keywords: ["breach", "ransomware", "exploit", "leak", "hacker", "zero-day", "data breach"] },
  { name: "space", keywords: ["solar flare", "cme", "geomagnetic storm", "space weather", "sun eruption", "aurora"] },
  { name: "aviation", keywords: ["airport closure", "ground stop", "flight diversion", "emergency landing", "near miss"] },
  { name: "earth", keywords: ["earthquake", "tsunami", "volcano", "eruption", "magnitude"] },
  { name: "finance", keywords: ["market crash", "circuit breaker", "default", "bank run", "bailout"] },
];

export function scoreSignals(items, extraSignals = []) {
  const all = [...SIGNALS, ...extraSignals];
  return all.map((s) => {
    let score = 0;
    const hits = [];
    for (const it of items) {
      const t = `${it.title || ""} ${it.summary || ""} ${it.source || ""}`.toLowerCase();
      for (const k of s.keywords) {
        if (t.includes(k.toLowerCase())) {
          score += 1;
          if (hits.length < 5) hits.push(it.title);
        }
      }
    }
    return { ...s, score, active: score > 0, hits };
  });
}

// User-defined alerts (keyword clusters) — CRUD via localStorage.
const ALERT_KEY = "hearthnet_alerts";

export function loadAlerts() {
  try {
    return JSON.parse(localStorage.getItem(ALERT_KEY) || "[]");
  } catch {
    return [];
  }
}

export function saveAlerts(alerts) {
  localStorage.setItem(ALERT_KEY, JSON.stringify(alerts));
}

export function addAlert(name, keywordsCsv) {
  const alerts = loadAlerts();
  const keywords = keywordsCsv.split(",").map((k) => k.trim()).filter(Boolean);
  alerts.push({ name, keywords });
  saveAlerts(alerts);
  return alerts;
}

export function removeAlert(name) {
  const alerts = loadAlerts().filter((a) => a.name !== name);
  saveAlerts(alerts);
  return alerts;
}
