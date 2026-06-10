"""Mobile static assets — PWA manifest, service worker, offline HTML.

Served by HttpServer at:
  GET /mobile/manifest.json   — PWA manifest
  GET /mobile/sw.js           — service worker
  GET /mobile/               — installable HTML wrapper

These let users install HearthNet on mobile home screens without an app store.
The Flutter native app (M22, separate repo) uses the same REST API.
"""

from __future__ import annotations

import json

# ---------------------------------------------------------------------------
# PWA Manifest
# ---------------------------------------------------------------------------

PWA_MANIFEST: dict = {
    "name": "HearthNet",
    "short_name": "HearthNet",
    "description": "Community-owned local AI mesh — works offline.",
    "start_url": "/",
    "display": "standalone",
    "background_color": "#1a1a2e",
    "theme_color": "#7c3aed",
    "orientation": "portrait-primary",
    "lang": "de-DE",
    "icons": [
        {
            "src": "/static/icon-192.png",
            "sizes": "192x192",
            "type": "image/png",
            "purpose": "any maskable",
        },
        {
            "src": "/static/icon-512.png",
            "sizes": "512x512",
            "type": "image/png",
            "purpose": "any maskable",
        },
    ],
    "shortcuts": [
        {
            "name": "Ask",
            "url": "/?tab=ask",
            "description": "Ask the local AI",
        },
        {
            "name": "Emergency",
            "url": "/?tab=emergency",
            "description": "Connectivity status",
        },
    ],
    "categories": ["utilities", "productivity"],
    "screenshots": [],
}

PWA_MANIFEST_JSON: str = json.dumps(PWA_MANIFEST, indent=2)

# ---------------------------------------------------------------------------
# Minimal Service Worker
# ---------------------------------------------------------------------------

SERVICE_WORKER_JS: str = """\
/* HearthNet service worker — minimal offline cache */
const CACHE = "hearthnet-v1";
const OFFLINE_FALLBACK = "/mobile/";

self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(CACHE).then((c) =>
      c.addAll([OFFLINE_FALLBACK, "/", "/mobile/manifest.json"])
    )
  );
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))
      )
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (e) => {
  if (e.request.method !== "GET") return;
  e.respondWith(
    fetch(e.request)
      .then((resp) => {
        const clone = resp.clone();
        caches.open(CACHE).then((c) => c.put(e.request, clone));
        return resp;
      })
      .catch(() => caches.match(e.request).then((r) => r || caches.match(OFFLINE_FALLBACK)))
  );
});
"""

# ---------------------------------------------------------------------------
# Installable HTML wrapper
# ---------------------------------------------------------------------------


def build_mobile_html(node_url: str = "", node_name: str = "HearthNet") -> str:
    """Return a minimal HTML page that registers the service worker and offers
    an install prompt. Works as a standalone PWA shell around the Gradio UI."""
    manifest_url = f"{node_url}/mobile/manifest.json"
    return f"""<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="theme-color" content="#7c3aed">
  <title>{node_name}</title>
  <link rel="manifest" href="{manifest_url}">
  <link rel="apple-touch-icon" href="/static/icon-192.png">
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: system-ui, sans-serif;
      background: #1a1a2e;
      color: #e2e8f0;
      min-height: 100dvh;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: 1.5rem;
      padding: 1.5rem;
    }}
    .logo {{ font-size: 3rem; }}
    h1 {{ font-size: 1.5rem; font-weight: 700; color: #a78bfa; }}
    p {{ text-align: center; color: #94a3b8; max-width: 22rem; }}
    .btn {{
      background: #7c3aed;
      color: #fff;
      border: none;
      border-radius: 0.75rem;
      padding: 0.9rem 2rem;
      font-size: 1rem;
      font-weight: 600;
      cursor: pointer;
      text-decoration: none;
      display: inline-block;
    }}
    .btn:hover {{ background: #6d28d9; }}
    .status {{
      font-size: 0.8rem;
      color: #64748b;
      text-align: center;
    }}
    #install-btn {{ display: none; }}
  </style>
</head>
<body>
  <div class="logo">&#x1F525;</div>
  <h1>{node_name}</h1>
  <p>Community-owned local AI mesh. Works even without internet.</p>

  <a class="btn" href="{node_url or '/'}">Open HearthNet</a>
  <button class="btn" id="install-btn">Add to Home Screen</button>

  <div class="status" id="status">Checking node status…</div>

  <script>
    // Service worker registration
    if ("serviceWorker" in navigator) {{
      navigator.serviceWorker.register("/mobile/sw.js").catch(() => {{}});
    }}

    // PWA install prompt
    let deferredPrompt;
    window.addEventListener("beforeinstallprompt", (e) => {{
      e.preventDefault();
      deferredPrompt = e;
      document.getElementById("install-btn").style.display = "inline-block";
    }});
    document.getElementById("install-btn").addEventListener("click", () => {{
      if (deferredPrompt) {{
        deferredPrompt.prompt();
        deferredPrompt.userChoice.then(() => {{ deferredPrompt = null; }});
      }}
    }});

    // Node status check
    fetch("{node_url}/health")
      .then((r) => r.json())
      .then((d) => {{
        document.getElementById("status").textContent =
          d.status === "ok" ? "Node online" : "Node degraded";
      }})
      .catch(() => {{
        document.getElementById("status").textContent = "Node unreachable — offline mode";
      }});
  </script>
</body>
</html>
"""
