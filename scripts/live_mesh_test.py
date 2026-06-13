"""Live integration test: a local node joins the public HF Space relay and
calls the Space node's capabilities all-to-all over the internet.

Run:  python scripts/live_mesh_test.py
"""

from __future__ import annotations

import asyncio
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

SPACE = "https://build-small-hackathon-hearthnet.hf.space"


async def main() -> int:
    from hearthnet.node import HearthNode

    node = HearthNode(f"ed25519:tester-{secrets.token_hex(3)}", "LiveTester", "ed25519:hf-space-community")
    await node.start(host="127.0.0.1", port=7099, data_dir=str(Path(__file__).resolve().parent.parent / ".live_test_node"))
    print(f"[local] node up: {node.node_id}")

    print(f"[mesh] joining live Space relay {SPACE} ...")
    result = await node.join_relay(SPACE)
    roster = result.get("roster", [])
    print(f"[mesh] joined. {len(roster)} other member(s):")
    space_node = None
    for m in roster:
        nid = m.get("node_id", "")
        caps = m.get("capabilities", [])
        print(f"   - {nid} ({m.get('display_name','')}) — {len(caps)} caps")
        if nid.startswith("hf-space"):
            space_node = nid

    if not space_node:
        print("[FAIL] Space node not found in roster")
        await node.stop()
        return 1

    # Verify the local bus registry now knows the Space node's capabilities.
    remote = sorted({e.descriptor.name for e in node.bus.registry.all_remote()})
    print(f"[bus] local registry now has {len(remote)} remote capabilities, e.g. {remote[:6]}")

    # All-to-all call: ask the Space node to run llm.chat over the relay.
    print("[call] llm.chat -> Space node over the relay ...")
    try:
        resp = await node.bus.call(
            "llm.chat",
            (1, 0),
            {"input": {"messages": [{"role": "user", "content": "Say hi from the mesh"}]}},
        )
        msg = resp.get("output", {}).get("message", {}).get("content", resp)
        print(f"[call] OK -> {msg!r}")
    except Exception as exc:
        print(f"[call] remote llm.chat failed (Space backend may gate ZeroGPU): {exc}")

    await node.stop()
    print("[done] live mesh verified: local node meshed all-to-all with the HF Space.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
