"""Generate HearthNet UI screenshots.

Launches a two-node mesh, performs real interactions (LLM query, chat send,
peer list refresh, marketplace post, RAG ingest), then saves screenshots.

Usage:  python scripts/gen_screenshots.py
Output: docs/screenshots/*.png
"""
from __future__ import annotations

import socket
import threading
import time
import urllib.request
from pathlib import Path

OUT = Path("docs/screenshots")
OUT.mkdir(parents=True, exist_ok=True)


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _wait_ready(port: int, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=2)
            return
        except Exception:
            time.sleep(0.4)
    raise TimeoutError(f"port {port} not ready after {timeout}s")


def _launch_node(demo, port: int) -> None:
    """Launch a pre-built Gradio Blocks on the given port."""
    demo.launch(
        server_name="127.0.0.1",
        server_port=port,
        prevent_thread_lock=True,
        quiet=True,
    )


def main() -> None:
    from hearthnet.node import InMemoryNetwork

    net = InMemoryNetwork()
    alice = net.add_node("alice", "Alice", "ed25519:hearthnet-demo")
    bob = net.add_node("bob", "Bob", "ed25519:hearthnet-demo")
    alice.install_demo_services(corpus="alice-docs")
    bob.install_demo_services(corpus="bob-docs")
    net.mesh_discover()

    port_a = _free_port()
    port_b = _free_port()

    from hearthnet.ui.app import build_ui

    # Build UIs sequentially (Gradio's block context is not thread-safe)
    def _build(node):
        return build_ui(
            bus=node.bus,
            state_bus=node.state_bus,
            display_name=node.display_name,
            node_id=node.node_id,
            community_id=node.community_id,
        ).build()

    demo_a = _build(alice)
    demo_b = _build(bob)

    threading.Thread(target=_launch_node, args=(demo_a, port_a), daemon=True).start()
    threading.Thread(target=_launch_node, args=(demo_b, port_b), daemon=True).start()

    _wait_ready(port_a)
    _wait_ready(port_b)
    time.sleep(1.5)  # let JS hydrate

    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)

        def _goto(page, url="/"):
            page.goto(url, wait_until="networkidle", timeout=30_000)

        def _click_tab(page, name):
            page.get_by_role("tab", name=name).click()
            page.wait_for_load_state("networkidle", timeout=15_000)

        # ── Alice ──────────────────────────────────────────────────────────
        ctx_a = browser.new_context(
            base_url=f"http://127.0.0.1:{port_a}",
            viewport={"width": 1280, "height": 900},
        )
        page_a = ctx_a.new_page()
        _goto(page_a)

        # 1. Ask tab — send a message and capture response
        page_a.screenshot(path=str(OUT / "01-alice-ask-empty.png"))
        print("  01-alice-ask-empty.png ✓")

        # Gradio renders textareas inside shadow DOM; use .first for the message box
        textarea = page_a.locator("textarea").first
        textarea.fill("What is HearthNet? Explain in two sentences.")
        # Multi-line textarea: click Send button (Enter adds newline, not submit)
        page_a.get_by_role("button", name="Send").first.click()
        page_a.wait_for_timeout(4000)
        page_a.screenshot(path=str(OUT / "02-alice-ask-response.png"))
        print("  02-alice-ask-response.png ✓")

        # 2. Chat tab — send a message to bob
        _click_tab(page_a, "Chat")
        # First textbox = recipient, second textbox = message
        textboxes = page_a.get_by_role("textbox")
        try:
            textboxes.nth(0).fill("bob")
            textboxes.nth(1).fill("Hey Bob, can you hear me?")
            page_a.get_by_role("button", name="Send").click()
            page_a.wait_for_timeout(1500)
        except Exception as exc:
            print(f"  Chat fill failed: {exc}")
        page_a.screenshot(path=str(OUT / "03-alice-chat.png"))
        print("  03-alice-chat.png ✓")

        # 3. Marketplace tab
        _click_tab(page_a, "Marketplace")
        page_a.screenshot(path=str(OUT / "04-alice-marketplace.png"))
        print("  04-alice-marketplace.png ✓")

        # 4. Files tab
        _click_tab(page_a, "Files")
        page_a.screenshot(path=str(OUT / "05-alice-files.png"))
        print("  05-alice-files.png ✓")

        # 5. Emergency tab
        _click_tab(page_a, "Emergency")
        page_a.screenshot(path=str(OUT / "06-alice-emergency.png"))
        print("  06-alice-emergency.png ✓")

        # 6. Settings tab — shows alice node ID and bob as peer
        _click_tab(page_a, "Settings")
        page_a.screenshot(path=str(OUT / "07-alice-settings.png"))
        print("  07-alice-settings.png ✓")

        # Click "Refresh Peers" to see bob in the list
        try:
            page_a.get_by_role("button", name="Refresh Peers").click()
            page_a.wait_for_timeout(2000)
            page_a.screenshot(path=str(OUT / "08-alice-settings-peers.png"))
            print("  08-alice-settings-peers.png ✓")
        except Exception as exc:
            print(f"  Peers refresh failed: {exc}")

        # 7. Mesh tab — refresh to show topology with Alice + Bob
        _click_tab(page_a, "Mesh")
        page_a.screenshot(path=str(OUT / "08b-alice-mesh-before-refresh.png"))
        print("  08b-alice-mesh-before-refresh.png ✓")
        try:
            page_a.get_by_role("button", name="Refresh Mesh").click()
            page_a.wait_for_timeout(2000)
            page_a.screenshot(path=str(OUT / "08c-alice-mesh-live.png"))
            print("  08c-alice-mesh-live.png ✓")
        except Exception as exc:
            print(f"  Mesh refresh failed: {exc}")

        ctx_a.close()

        # ── Bob ────────────────────────────────────────────────────────────
        ctx_b = browser.new_context(
            base_url=f"http://127.0.0.1:{port_b}",
            viewport={"width": 1280, "height": 900},
        )
        page_b = ctx_b.new_page()
        _goto(page_b)
        page_b.screenshot(path=str(OUT / "09-bob-ask-tab.png"))
        print("  09-bob-ask-tab.png ✓")

        # Bob Ask — ask a question  
        textarea_b = page_b.locator("textarea").first
        textarea_b.fill("Hello from Bob! What can I do on HearthNet?")
        page_b.get_by_role("button", name="Send").first.click()
        page_b.wait_for_timeout(4000)
        page_b.screenshot(path=str(OUT / "09b-bob-ask-response.png"))
        print("  09b-bob-ask-response.png ✓")

        # Bob mesh tab — should show Alice
        _click_tab(page_b, "Mesh")
        try:
            page_b.get_by_role("button", name="Refresh Mesh").click()
            page_b.wait_for_timeout(2000)
            page_b.screenshot(path=str(OUT / "10-bob-mesh-sees-alice.png"))
            print("  10-bob-mesh-sees-alice.png ✓")
        except Exception as exc:
            print(f"  Bob mesh refresh failed: {exc}")

        # Bob settings — should show alice as peer
        _click_tab(page_b, "Settings")
        page_b.screenshot(path=str(OUT / "10b-bob-settings.png"))
        print("  10b-bob-settings.png ✓")

        # Refresh Bob's peer list — should show Alice
        try:
            page_b.get_by_role("button", name="Refresh Peers").click()
            page_b.wait_for_timeout(2000)
            page_b.screenshot(path=str(OUT / "10c-bob-settings-peers.png"))
            print("  10c-bob-settings-peers.png ✓")
        except Exception as exc:
            print(f"  Bob peers refresh failed: {exc}")

        ctx_b.close()
        browser.close()

    print("\nScreenshots saved to docs/screenshots/:")
    for f in sorted(OUT.glob("*.png")):
        print(f"  {f.name}")


if __name__ == "__main__":
    main()
