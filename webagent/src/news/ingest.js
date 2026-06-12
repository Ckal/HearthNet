// src/news/ingest.js
// Browser-only RSS/Atom ingestion. Feeds usually block cross-origin reads, so
// we route through public CORS proxies (with fallback) and parse with DOMParser.

// CORS proxies, best-first. allorigins `/get` returns { contents } with an
// Access-Control-Allow-Origin header; r.jina.ai returns readable text. Both
// are CORS-enabled. allorigins rate-limits bursts, so callers throttle.
const PROXIES = [
  { build: (u) => `https://api.allorigins.win/get?url=${encodeURIComponent(u)}`, json: true },
  { build: (u) => `https://r.jina.ai/${u}` },
];

async function fetchText(url, { signal } = {}) {
  let lastErr = null;
  for (const p of PROXIES) {
    try {
      const res = await fetch(p.build(url), { signal });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      let text;
      if (p.json) {
        const data = await res.json();
        text = data.contents || "";
      } else {
        text = await res.text();
      }
      if (text && text.length > 50) return text;
    } catch (err) {
      lastErr = err;
    }
  }
  throw lastErr || new Error("All proxies failed");
}

function text(node, sel) {
  const el = node.querySelector(sel);
  return el ? el.textContent.trim() : "";
}

function parseFeed(xml, sourceName) {
  const doc = new DOMParser().parseFromString(xml, "text/xml");
  if (doc.querySelector("parsererror")) return [];

  // RSS <item> or Atom <entry>
  const nodes = [...doc.querySelectorAll("item"), ...doc.querySelectorAll("entry")];
  return nodes.map((n) => {
    const title = text(n, "title");
    let link = text(n, "link");
    if (!link) {
      const a = n.querySelector("link");
      link = a?.getAttribute("href") || "";
    }
    const summary = text(n, "description") || text(n, "summary") || text(n, "content");
    const published = text(n, "pubDate") || text(n, "published") || text(n, "updated");
    return {
      title,
      link,
      summary: summary.replace(/<[^>]+>/g, "").slice(0, 400),
      source: sourceName,
      published,
      ts: published ? Date.parse(published) || Date.now() : Date.now(),
    };
  });
}

// Ingest a list of sources. Returns merged, de-duped, newest-first items.
// Fetches are throttled (small concurrent pool) so shared proxies don't
// rate-limit us and drop the CORS header on error responses.
export async function ingestSources(sources, { signal, onSource, concurrency = 3 } = {}) {
  const queue = [...sources];
  const collected = [];

  async function worker() {
    while (queue.length) {
      const s = queue.shift();
      try {
        const xml = await fetchText(s.url, { signal });
        const items = parseFeed(xml, s.name).map((it) => ({ ...it, cat: s.cat }));
        collected.push(...items);
        onSource?.({ source: s.name, count: items.length });
      } catch {
        onSource?.({ source: s.name, count: 0 });
      }
    }
  }

  await Promise.all(Array.from({ length: Math.min(concurrency, sources.length) }, worker));

  const merged = [];
  const seen = new Set();
  for (const it of collected) {
    const key = it.link || it.title;
    if (!key || seen.has(key)) continue;
    seen.add(key);
    merged.push(it);
  }
  merged.sort((a, b) => b.ts - a.ts);
  return merged;
}

// Generic readable-text scrape via r.jina.ai (CORS-friendly, returns markdown).
export async function scrapeUrl(url, { signal } = {}) {
  const res = await fetch(`https://r.jina.ai/${url}`, { signal });
  if (!res.ok) throw new Error(`scrape failed: HTTP ${res.status}`);
  return (await res.text()).slice(0, 12000);
}

// Web search via Google News RSS (good for current events; CORS-proxied).
export async function webSearchNews(query, { signal } = {}) {
  const url = `https://news.google.com/rss/search?q=${encodeURIComponent(query)}&hl=en-US&gl=US&ceid=US:en`;
  const xml = await fetchText(url, { signal });
  const items = parseFeed(xml, "Google News").slice(0, 8);
  if (!items.length) return "No results.";
  return items.map((it, i) => `${i + 1}. ${it.title}\n   ${it.link}`).join("\n");
}
