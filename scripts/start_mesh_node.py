"""HearthNet mesh launcher — start a local node, optionally join the internet mesh.

Local-first by design:

    python scripts/start_mesh_node.py
        → starts a pure local node (mDNS/UDP discovery + local HTTP server).
          Makes NO outbound internet calls.

    python scripts/start_mesh_node.py --connect hf
        → also joins the public HF Space relay hub, so this node meshes
          all-to-all with every other connected node over NAT.

    python scripts/start_mesh_node.py --connect <invite-or-relay-url>
        → joins the relay hub embedded in an invite (hn1:...) or given directly.

The node stays running (Ctrl-C to stop). While connected, inbound bus calls from
other mesh members are served locally and your calls route to them transparently.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import secrets

HF_SPACE_URL = "https://build-small-hackathon-hearthnet.hf.space"


def _resolve_relay(connect: str) -> str:
    """Map a --connect value to a relay base URL.

    Accepts ``hf`` (the public Space), an ``hn1:`` invite (relay extracted), or a
    raw http(s) relay URL.
    """
    if connect in ("hf", "space"):
        return HF_SPACE_URL
    if connect.startswith("hn1:"):
        from hearthnet.ui.onboarding import decode_invite

        blob = decode_invite(connect)
        if not blob.relay_url:
            raise SystemExit("invite has no relay_url embedded")
        return blob.relay_url
    if connect.startswith(("http://", "https://")):
        return connect.rstrip("/")
    raise SystemExit(f"unrecognised --connect value: {connect!r}")


async def _run(args: argparse.Namespace) -> int:
    from hearthnet.node import HearthNode

    node_id = args.node_id or f"ed25519:mesh-{secrets.token_hex(4)}"
    node = HearthNode(node_id, args.name, args.community)

    if args.demo_services:
        node.install_demo_services(corpus="demo")
    else:
        with contextlib.suppress(Exception):
            node.install_services(corpus="community")

    local_caps = sorted({e.descriptor.name for e in node.bus.registry.all_local()})
    print(f"[node] {node.display_name} ({node_id})")
    print(f"[node] local capabilities: {local_caps}")

    await node.start(host=args.host, port=args.port)
    print(f"[node] local HTTP server on {args.host}:{args.port} (local-first)")

    if args.connect:
        relay_url = _resolve_relay(args.connect)
        print(f"[mesh] joining relay hub {relay_url} ...")
        try:
            result = await node.join_relay(relay_url, token=args.token or None)
        except Exception as exc:  # surface a clear startup error, keep node local
            print(f"[mesh] x relay join failed: {exc}")
            print("       The Space may be asleep/building. Open its UI once and retry.")
        else:
            members = [m.get("node_id", "")[:24] for m in result.get("roster", [])]
            print(f"[mesh] + joined. {len(members)} other member(s): {members}")
            print("[mesh] all-to-all: your bus calls now route to mesh peers over NAT.")
    else:
        print("[mesh] running local-only (no relay). Use --connect hf to mesh.")

    print("[node] up. Press Ctrl-C to stop.")
    stop = asyncio.Event()
    try:
        await stop.wait()
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        print("\n[node] shutting down ...")
        await node.stop()
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Start a HearthNet mesh node")
    parser.add_argument("--name", default="Mesh Node", help="display name")
    parser.add_argument("--node-id", default="", help="full node id (default: random)")
    parser.add_argument("--community", default="ed25519:community", help="community id")
    parser.add_argument("--host", default="127.0.0.1", help="local HTTP bind host")
    parser.add_argument("--port", type=int, default=7080, help="local HTTP port")
    parser.add_argument(
        "--connect",
        default="",
        help="'hf', an hn1: invite, or a relay URL to join the internet mesh",
    )
    parser.add_argument("--token", default="", help="optional relay join token")
    parser.add_argument(
        "--demo-services",
        action="store_true",
        help="install fast echo/demo services instead of real local backends",
    )
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
