"""
HearthNet PWA Enhancement

Adds Progressive Web App support to the Gradio UI:
- Service worker for offline caching
- Web app manifest for installability
- Push notifications support
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse


def setup_pwa(app: FastAPI, static_dir: Path) -> None:
    """
    Set up PWA support for HearthNet Gradio UI.
    
    Args:
        app: FastAPI application instance
        static_dir: Directory where PWA files are served from
    """

    # Serve manifest.json
    @app.get("/manifest.json")
    async def get_manifest():
        manifest_path = Path(__file__).parent / "manifest.json"
        if manifest_path.exists():
            return FileResponse(manifest_path, media_type="application/manifest+json")
        # Fallback manifest
        return {
            "name": "HearthNet",
            "short_name": "HearthNet",
            "description": "Local-first community AI mesh",
            "start_url": "/",
            "display": "standalone",
            "theme_color": "#1e40af",
            "background_color": "#ffffff",
            "icons": [
                {
                    "src": "/static/icon-192.png",
                    "sizes": "192x192",
                    "type": "image/png",
                }
            ],
        }

    # Serve service worker
    @app.get("/sw.js")
    async def get_service_worker():
        sw_path = Path(__file__).parent / "sw.js"
        if sw_path.exists():
            return FileResponse(sw_path, media_type="application/javascript")
        return {"error": "Service worker not found"}

    # Inject PWA meta tags into HTML
    @app.middleware("http")
    async def inject_pwa_headers(request, call_next):
        response = await call_next(request)

        # Only modify HTML responses
        if "text/html" in response.headers.get("content-type", ""):
            # Read body
            body = b""
            async for chunk in response.body_iterator:
                body += chunk

            # Inject PWA tags
            pwa_tags = """
    <link rel="manifest" href="/manifest.json">
    <meta name="theme-color" content="#1e40af">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <meta name="apple-mobile-web-app-title" content="HearthNet">
    <script>
        if ('serviceWorker' in navigator) {
            navigator.serviceWorker.register('/sw.js').then(reg => {
                console.log('[PWA] Service Worker registered', reg);
            }).catch(err => {
                console.warn('[PWA] Service Worker registration failed:', err);
            });
        }
    </script>
"""

            # Insert before </head>
            if b"</head>" in body:
                body = body.replace(b"</head>", pwa_tags.encode() + b"</head>", 1)

            # Create new response with modified content
            from starlette.responses import Response as StarletteResponse
            response = StarletteResponse(
                content=body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )

        return response

    print("✅ PWA support enabled")
    print("   - Manifest: /manifest.json")
    print("   - Service Worker: /sw.js")
    print("   - Installable from mobile browsers")


__all__ = ["setup_pwa"]
