"""Two-node HearthNet demo.

Launches two fully-wired HearthNet nodes in the same process using the
InMemoryNetwork transport.  Both nodes:
  - have demo services (LLM echo, RAG, Marketplace, Chat)
  - discover each other (shared InMemoryTransport)
  - start a Gradio UI on separate ports

Node A  →  http://127.0.0.1:7861   (Alice)
Node B  →  http://127.0.0.1:7862   (Bob)

Run:
    python scripts/demo_two_nodes.py
"""
from __future__ import annotations

import threading
import time

from hearthnet.node import HearthNode, InMemoryNetwork
from hearthnet.ui.app import build_ui


def launch_node(
    node: HearthNode,
    port: int,
    *,
    share: bool = False,
) -> None:
    """Build and launch Gradio for a single node (blocking)."""
    ui = build_ui(
        bus=node.bus,
        state_bus=node.state_bus,
        display_name=node.display_name,
        node_id=node.node_id,
        community_id=node.community_id,
    )
    demo = ui.build()
    print(f"[{node.display_name}] UI → http://127.0.0.1:{port}/")
    demo.launch(
        server_name="0.0.0.0",
        server_port=port,
        share=share,
        quiet=True,
    )


def main() -> None:
    net = InMemoryNetwork()

    # Create two named nodes in the same community
    alice = net.add_node("alice", "Alice", "ed25519:hearthnet-demo")
    bob = net.add_node("bob", "Bob", "ed25519:hearthnet-demo")

    # Install real (local) demo services on both
    alice.install_demo_services(corpus="alice-knowledge")
    bob.install_demo_services(corpus="bob-knowledge")

    # Let them discover each other via in-memory transport
    net.mesh_discover()

    print("Peers registered:")
    for n in [alice, bob]:
        peers = [p.node_id for p in n.peers.all()]
        caps = [e.descriptor.name for e in n.bus.registry.all_local()]
        print(f"  {n.node_id}: peers={peers}, local_caps={caps}")

    # Launch both UIs — node B in a daemon thread, node A blocks main
    t = threading.Thread(
        target=launch_node, args=(bob, 7862), kwargs={"share": False}, daemon=True
    )
    t.start()
    time.sleep(2)  # give Bob time to bind

    print("\nBoth nodes are running:")
    print("  Alice (Node A): http://127.0.0.1:7861/")
    print("  Bob   (Node B): http://127.0.0.1:7862/")
    print("\nIn the Chat tab on Alice, enter 'bob' as recipient to message Bob.")
    print("In the Ask tab, type any question to see the LLM echo response.")

    launch_node(alice, 7861)  # blocks


if __name__ == "__main__":
    main()
