"""Mobile static app helpers (M08 / M22 anchor-side).

Provides:
  - PWA manifest JSON for the Gradio app
  - A minimal offline-capable service worker stub
  - A thin HTML wrapper for mobile home-screen installation

These are served by HttpServer when present. The Flutter native app (M22)
communicates with the node via the same REST/WebSocket API as the browser.
"""

from __future__ import annotations

from hearthnet.ui.mobile.static import (
    PWA_MANIFEST,
    SERVICE_WORKER_JS,
    build_mobile_html,
)

__all__ = ["PWA_MANIFEST", "SERVICE_WORKER_JS", "build_mobile_html"]
