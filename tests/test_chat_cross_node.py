"""Integration test: cross-node chat delivery (M10).

Verifies that chat.send from node A to node B:
 - calls chat.deliver on B's bus
 - B stores the message
 - chat.history on B shows the message
 - delivery status is "delivered" (not "queued" or "direct")

Uses in-process InMemoryTransport so no relay/HTTP needed.
"""
from __future__ import annotations

import pytest
from hearthnet.bus import InMemoryTransport


@pytest.fixture()
def two_nodes():
    from hearthnet.node import HearthNode

    net = InMemoryTransport()
    alice = HearthNode("node-alice", "Alice", "ed25519:test", transport=net)
    alice.install_demo_services()
    net.register(alice.bus)

    bob = HearthNode("node-bob", "Bob", "ed25519:test", transport=net)
    bob.install_demo_services()
    net.register(bob.bus)

    return alice, bob


@pytest.mark.asyncio
async def test_chat_send_cross_node_delivers(two_nodes):
    alice, bob = two_nodes

    r = await alice.bus.call(
        "chat.send", (1, 0), {"input": {"recipient": "node-bob", "body": "Hello Bob!"}}
    )
    status = r.get("output", {}).get("delivered")
    assert status == "delivered", f"Expected 'delivered', got {status!r}"


@pytest.mark.asyncio
async def test_chat_history_shows_received_message(two_nodes):
    alice, bob = two_nodes

    await alice.bus.call(
        "chat.send", (1, 0), {"input": {"recipient": "node-bob", "body": "Hi from Alice"}}
    )

    r = await bob.bus.call("chat.history", (1, 0), {"input": {"peer": "node-alice"}})
    msgs = r.get("output", {}).get("messages", [])
    assert len(msgs) == 1, f"Expected 1 message in Bob's history, got {len(msgs)}"
    assert msgs[0]["body"] == "Hi from Alice"
    assert msgs[0]["from"] == "node-alice"


@pytest.mark.asyncio
async def test_self_send_returns_direct(two_nodes):
    alice, _ = two_nodes
    r = await alice.bus.call(
        "chat.send", (1, 0), {"input": {"recipient": "node-alice", "body": "hi me"}}
    )
    status = r.get("output", {}).get("delivered")
    assert status == "direct", f"Expected 'direct' for self-send, got {status!r}"


@pytest.mark.asyncio
async def test_send_to_unknown_node_returns_queued(two_nodes):
    alice, _ = two_nodes
    r = await alice.bus.call(
        "chat.send", (1, 0), {"input": {"recipient": "node-nobody", "body": "hello?"}}
    )
    status = r.get("output", {}).get("delivered")
    assert status == "queued", f"Expected 'queued' for unknown node, got {status!r}"


@pytest.mark.asyncio
async def test_manually_wired_chat_service_delivers():
    """Regression: a ChatService registered manually (as app.py / the HF Space
    entry point does) must receive a ``bus=`` reference, otherwise
    ``_deliver_remote`` short-circuits to ``"queued"`` before attempting
    delivery. Mirrors the app.py wiring to guard against that regression.
    """
    from hearthnet.node import HearthNode
    from hearthnet.services.chat.service import ChatService

    net = InMemoryTransport()
    alice = HearthNode("node-alice", "Alice", "ed25519:test", transport=net)
    # Wire chat exactly like app.py: explicit bus= argument is required.
    alice.bus.register_service(ChatService(alice.node_id, bus=alice.bus))
    net.register(alice.bus)

    bob = HearthNode("node-bob", "Bob", "ed25519:test", transport=net)
    bob.bus.register_service(ChatService(bob.node_id, bus=bob.bus))
    net.register(bob.bus)

    r = await alice.bus.call(
        "chat.send", (1, 0), {"input": {"recipient": "node-bob", "body": "wired"}}
    )
    assert r.get("output", {}).get("delivered") == "delivered"


@pytest.mark.asyncio
async def test_chat_service_without_bus_cannot_deliver():
    """A ChatService constructed without a bus reference can only queue —
    documents the failure mode the app.py wiring fix prevents.
    """
    from hearthnet.services.chat.service import ChatService

    svc = ChatService("node-alice")  # no bus=
    status = await svc._deliver_remote(
        {"to": "node-bob", "from": "node-alice", "body": "x", "event_id": "e1"}
    )
    assert status == "queued"

