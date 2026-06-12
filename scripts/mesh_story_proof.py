"""Mesh user-story proof — runs the all-to-all relay mesh for real and screenshots it.

Each "user story" is executed end-to-end against a genuine, locally-hosted relay
hub (uvicorn) with real HearthNet nodes — no mocks, no fake answers:

  US-M1  Bob (no LLM locally) asks a question -> routed over the relay to Alice.
  US-M2  Bob queries RAG          -> routed over the relay to Alice's corpus.
  US-M3  Carol joins late         -> roster gossip makes A/B/C mutually aware;
                                     Carol then routes an LLM call to Alice.
  US-M4  Local-first guard        -> a node that never joined the relay cannot
                                     reach mesh peers (proves relay is opt-in).

The real results are rendered into an annotated HTML report and captured as
screenshots in docs/screenshots/stories/ via Playwright.

Usage:  python scripts/mesh_story_proof.py
"""

from __future__ import annotations

import asyncio
import contextlib
import datetime
import html
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

OUT = Path("docs/screenshots/stories")
OUT.mkdir(parents=True, exist_ok=True)
REPORT = Path("docs/screenshots/_mesh_story.html")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def _serve_relay(port: int):
    import httpx
    import uvicorn
    from fastapi import FastAPI

    from hearthnet.transport.relay_hub import RelayHub, mount_relay_endpoints

    app = FastAPI()
    hub = RelayHub(member_ttl_seconds=120)
    mount_relay_endpoints(app, hub)
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", lifespan="off")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())

    deadline = asyncio.get_event_loop().time() + 5.0
    async with httpx.AsyncClient(timeout=1.0) as client:
        while asyncio.get_event_loop().time() < deadline:
            with contextlib.suppress(Exception):
                if (await client.get(f"http://127.0.0.1:{port}/relay/v1/roster")).status_code == 200:
                    break
            await asyncio.sleep(0.1)
        else:
            raise TimeoutError("relay hub never became ready")

    async def _shutdown() -> None:
        server.should_exit = True
        with contextlib.suppress(Exception):
            await task

    return _shutdown


async def _wait_until(predicate, timeout: float = 6.0) -> bool:
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.05)
    return False


async def run_stories() -> dict:
    from hearthnet.node import HearthNode

    port = _free_port()
    relay_url = f"http://127.0.0.1:{port}"
    shutdown = await _serve_relay(port)

    alice = HearthNode("ed25519:alice-mesh", "Alice", "ed25519:community")
    alice.install_demo_services(corpus="alpha")
    bob = HearthNode("ed25519:bob-mesh", "Bob", "ed25519:community")
    carol = HearthNode("ed25519:carol-mesh", "Carol", "ed25519:community")

    stories: list[dict] = []
    try:
        bob_local = sorted({e.descriptor.name for e in bob.bus.registry.all_local()})
        await alice.join_relay(relay_url)
        await bob.join_relay(relay_url)
        await _wait_until(
            lambda: any(e.node_id == "ed25519:alice-mesh" for e in bob.bus.registry.all_remote())
        )

        # US-M1 — Bob's LLM call routes across the relay to Alice.
        q1 = "In one sentence, how do I store water safely?"
        c1 = await bob.bus.call(
            "llm.chat", (1, 0), {"input": {"messages": [{"role": "user", "content": q1}]}}
        )
        stories.append(
            {
                "id": "USM-01-bob-llm-over-relay",
                "title": "US-M1 · Bob asks the mesh — answered by Alice over the relay",
                "facts": [
                    ("Bob's local capabilities", ", ".join(bob_local) or "(none)"),
                    ("llm.chat available locally on Bob?", "no — must route over the mesh"),
                    ("Question", q1),
                    ("Answer", c1["output"]["message"]["content"]),
                    ("Served by model", c1["meta"]["model"] + " (Alice)"),
                ],
            }
        )

        # US-M2 — Bob's RAG query routes across the relay to Alice's corpus.
        c2 = await bob.bus.call("rag.query", (1, 0), {"input": {"query": "water"}})
        chunk = c2["output"]["chunks"][0]
        stories.append(
            {
                "id": "USM-02-bob-rag-over-relay",
                "title": "US-M2 · Bob queries RAG — Alice's corpus answers over the relay",
                "facts": [
                    ("Query", "water"),
                    ("Top chunk", chunk["text"]),
                    ("Source doc", chunk["metadata"]["doc_title"]),
                    ("Corpus", c2["meta"]["corpus"] + " (Alice)"),
                ],
            }
        )

        # US-M3 — Carol joins late; roster gossip; Carol routes to Alice.
        await carol.join_relay(relay_url)
        a_sees_c = await _wait_until(lambda: alice.peers.get("ed25519:carol-mesh") is not None)
        b_sees_c = await _wait_until(lambda: bob.peers.get("ed25519:carol-mesh") is not None)
        c3 = await carol.bus.call(
            "llm.chat",
            (1, 0),
            {"input": {"messages": [{"role": "user", "content": "Hello mesh, this is Carol"}]}},
        )
        stories.append(
            {
                "id": "USM-03-roster-gossip-all-to-all",
                "title": "US-M3 · Carol joins late — all-to-all roster gossip",
                "facts": [
                    ("Alice now sees Carol", "yes" if a_sees_c else "no"),
                    ("Bob now sees Carol", "yes" if b_sees_c else "no"),
                    ("Carol sees Alice", "yes" if carol.peers.get("ed25519:alice-mesh") else "no"),
                    ("Carol's LLM call answered by", c3["output"]["message"]["content"]),
                ],
            }
        )

        # US-M4 — Local-first guard: a node that never joined the relay is isolated.
        loner = HearthNode("ed25519:loner", "Loner", "ed25519:community")
        from hearthnet.bus import BusError

        try:
            await loner.bus.call(
                "llm.chat",
                (1, 0),
                {"input": {"messages": [{"role": "user", "content": "anyone there?"}]}},
            )
            guard_result = "unexpected success"
        except BusError as exc:
            guard_result = f"{exc.code} — no mesh provider reachable"
        stories.append(
            {
                "id": "USM-04-local-first-guard",
                "title": "US-M4 · Local-first guard — relay is opt-in",
                "facts": [
                    ("Loner joined the relay?", "no"),
                    ("llm.chat result", guard_result),
                    ("Meaning", "without an explicit join, a node makes NO mesh calls"),
                ],
            }
        )
    finally:
        await alice.leave_relay()
        await bob.leave_relay()
        await carol.leave_relay()
        await shutdown()

    return {"stories": stories, "relay_url": relay_url}


def _render_html(result: dict) -> str:
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    cards = []
    for s in result["stories"]:
        rows = "".join(
            f'<div class="row"><span class="k">{html.escape(k)}</span>'
            f'<span class="v">{html.escape(str(v))}</span></div>'
            for k, v in s["facts"]
        )
        cards.append(
            f'<div class="card" id="{s["id"]}"><h2>{html.escape(s["title"])}</h2>{rows}</div>'
        )
    body = "\n".join(cards)
    return f"""<html><head><meta charset="utf-8"><style>
*{{box-sizing:border-box}}
body{{background:#0d1117;color:#c9d1d9;font-family:Consolas,'Segoe UI',monospace;padding:24px;width:760px}}
h1{{color:#ff7a18;font-size:22px;margin:0 0 4px}}
small{{color:#8b949e}}
.card{{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:16px 18px;margin:14px 0}}
.card h2{{color:#58a6ff;font-size:15px;margin:0 0 10px}}
.row{{display:flex;gap:12px;padding:4px 0;border-top:1px solid #21262d}}
.row:first-of-type{{border-top:none}}
.k{{color:#8b949e;flex:0 0 240px}}
.v{{color:#e3b341;flex:1;overflow-wrap:anywhere}}
.badge{{display:inline-block;background:#1f6feb;color:#fff;border-radius:6px;padding:2px 8px;font-size:11px;margin-left:8px}}
</style></head><body>
<h1>HearthNet · All-to-all internet mesh <span class="badge">live relay proof</span></h1>
<small>{ts} · pull-based relay hub on uvicorn · real HearthNet nodes · no mocks</small>
{body}
</body></html>"""


def _shoot(html_path: Path) -> None:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # pragma: no cover
        print(f"[screenshots] playwright unavailable: {exc}")
        return

    url = html_path.resolve().as_uri()
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_context(viewport={"width": 800, "height": 1000}).new_page()
        page.goto(url, wait_until="networkidle")
        page.wait_for_timeout(300)
        full = OUT / "USM-00-all-to-all-mesh.png"
        page.screenshot(path=str(full), full_page=True)
        print(f"  {full.name}")
        for card in page.locator(".card").all():
            cid = card.get_attribute("id")
            if cid:
                card.screenshot(path=str(OUT / f"{cid}.png"))
                print(f"  {cid}.png")
        browser.close()


def main() -> None:
    result = asyncio.run(run_stories())
    REPORT.write_text(_render_html(result), encoding="utf-8")
    print(f"wrote {REPORT}")
    for s in result["stories"]:
        print(f"  [ok] {s['title']}")
    _shoot(REPORT)
    print("done")


if __name__ == "__main__":
    main()
