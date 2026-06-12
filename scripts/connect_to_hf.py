"""Connect a local HearthNet node to the public HuggingFace Space and route a
real capability call to it over HTTPS.

Usage:
    python scripts/connect_to_hf.py
    python scripts/connect_to_hf.py --ask "How do I purify water?"

What it does (all real, no mocks):
  1. Builds a local in-process HearthNet node (with discovery + HTTP transport).
  2. Calls ``discovery.peer.add`` -> fetches the Space's ``/manifest`` and
     registers its capabilities (llm.chat, rag.query, moe.*, ...) as remote
     routable entries.
  3. Routes an ``llm.chat`` (and ``rag.query``) call which the bus dispatches to
     the Space via ``POST https://<space>/bus/v1/call``.

Requires the Space to expose the bus endpoints (mounted in app.py). If the
Space is still building or asleep, peer.add returns a clear ``partition`` error.
"""

from __future__ import annotations

import argparse
import asyncio

HF_SPACE_URL = "https://build-small-hackathon-hearthnet.hf.space"


async def _run(space_url: str, question: str) -> int:
    from hearthnet.node import HearthNode

    node = HearthNode("ed25519:local-cli", "Local CLI", "ed25519:community")
    local_caps = sorted({e.descriptor.name for e in node.bus.registry.all_local()})
    print(f"[1/4] Local node up. Local capabilities: {local_caps}")

    print(f"[2/4] Peering with {space_url} via discovery.peer.add ...")
    add = await node.bus.call("discovery.peer.add", (1, 0), {"input": {"endpoint": space_url}})
    if add.get("error"):
        print(f"      x peer.add failed: {add['error']} - {add.get('message', '')}")
        print("        The Space may still be building or asleep. Open the UI once and retry.")
        return 1
    out = add["output"]
    print(f"      + Peer added: {out['node_id'][:24]}...")
    print(f"        Remote capabilities now routable: {out['capabilities']}")

    remote = sorted({e.descriptor.name for e in node.bus.registry.all_remote()})
    print(f"[3/4] Bus registry remote entries: {remote}")

    print(f'[4/4] Routing llm.chat to the Space - asking: "{question}"')
    try:
        chat = await node.bus.call(
            "llm.chat",
            (1, 0),
            {"input": {"messages": [{"role": "user", "content": question}]}},
        )
        msg = chat.get("output", {}).get("message", {}).get("content", "")
        meta = chat.get("meta", {})
        print(f"      + Space replied ({meta.get('model', '?')}):")
        print(f"        {msg.strip()[:500]}")
    except Exception as exc:
        print(f"      x llm.chat routing failed: {exc}")
        return 1

    print()
    print("=" * 62)
    print("  Connected. Your local node is peered with the HF Space and")
    print("  routed a real llm.chat call to it over HTTPS.")
    print("  RAG: node.bus.call('rag.query', (1,0), {'input': {'query': '...'}})")
    print("=" * 62)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Peer a local node with the HF Space")
    parser.add_argument("--space-url", default=HF_SPACE_URL)
    parser.add_argument("--ask", default="In one sentence, how do I store water safely?")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_run(args.space_url, args.ask)))


if __name__ == "__main__":
    main()
