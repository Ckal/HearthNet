"""Connect a local HearthNet node to the HuggingFace Space anchor.

Usage:
    python scripts/connect_to_hf.py [--local-port 7080]

This script:
1. Checks that a local HearthNet node is reachable at localhost:<local-port>
2. Adds the HF Space anchor as a known peer via discovery.peer.add
3. Verifies the peer appears in the registry
4. Prints instructions for what you can do next
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

HF_SPACE_URL = "https://build-small-hackathon-hearthnet.hf.space"
HF_NODE_ID = "hf-space-anchor"


def _call(host: str, port: int, capability: str, body: dict) -> dict:
    url = f"http://{host}:{port}/bus/v1/call"
    payload = json.dumps(
        {"capability": capability, "version": [1, 0], "body": body}
    ).encode()
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
            return json.loads(resp.read())
    except urllib.error.URLError as exc:
        raise SystemExit(f"[ERROR] Cannot reach local node at {host}:{port} — {exc}") from exc


def _check_hf_space() -> bool:
    try:
        with urllib.request.urlopen(f"{HF_SPACE_URL}/health", timeout=10) as r:  # noqa: S310
            return r.status == 200
    except Exception:
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Connect local node to HF Space anchor")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--local-port", type=int, default=7080)
    args = parser.parse_args()

    print(f"[1/4] Checking local node at {args.host}:{args.local_port} …")
    result = _call(args.host, args.local_port, "health", {})
    print(f"      ✓ Local node is running. Status: {result.get('output', {}).get('status', '?')}")

    print(f"[2/4] Checking HF Space at {HF_SPACE_URL} …")
    hf_ok = _check_hf_space()
    if not hf_ok:
        print("      ⚠ HF Space is not reachable (it may be sleeping). Continuing anyway …")
    else:
        print("      ✓ HF Space is reachable.")

    print("[3/4] Adding HF Space as a peer …")
    try:
        add_result = _call(
            args.host,
            args.local_port,
            "discovery.peer.add",
            {
                "input": {
                    "endpoint": HF_SPACE_URL,
                    "node_id": HF_NODE_ID,
                    "display_name": "HearthNet HF Space (anchor)",
                    "trust_level": "trusted",
                }
            },
        )
        print(f"      ✓ Peer added: {add_result.get('output', add_result)}")
    except SystemExit:
        raise
    except Exception as exc:
        print(f"      ✗ discovery.peer.add failed: {exc}")
        print("        (The capability may not be registered yet — run 'python -m hearthnet.cli run' first)")
        sys.exit(1)

    print("[4/4] Listing known peers …")
    peers_result = _call(args.host, args.local_port, "discovery.peers", {"input": {}})
    peers = peers_result.get("output", {}).get("peers", [])
    hf_found = any(p.get("node_id") == HF_NODE_ID for p in peers)
    if hf_found:
        print(f"      ✓ HF Space peer confirmed in registry ({len(peers)} total peers)")
    else:
        print(f"      ⚠ HF Space not yet in peer list ({len(peers)} peers found). May take a moment.")

    print()
    print("═" * 60)
    print("  Connected! Your local node is now peered with the HF Space.")
    print()
    print("  What you can do:")
    print("    • Route local LLM queries FROM the HF Space to your machine:")
    print("      The HF Space will prefer your node for llm.chat if it has")
    print("      a better model (Ollama, llama.cpp, etc.)")
    print()
    print("    • Push community posts to the shared mesh:")
    print(f"      python -m hearthnet.cli call marketplace.post.create 1 0 \\")
    print('        \'{"input": {"title": "Hello from local!", "body": "Test"}}\'')
    print()
    print("    • Pull model weights from HF Space blobs:")
    print(f"      python -m hearthnet.cli call model.list 1 0 \'{{}}\'")
    print()
    print(f"    • Local UI:    http://localhost:{args.local_port + 780}")
    print(f"    • HF Space UI: {HF_SPACE_URL}")
    print("═" * 60)


if __name__ == "__main__":
    main()
