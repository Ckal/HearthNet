"""Integration test: all-to-all mesh over a pull-based relay hub.

Proves the NAT-safe internet-mesh wiring (P1-P2):
  1. A real FastAPI relay hub runs on uvicorn (the role the HF Space plays).
  2. Node A (provides llm.chat + rag.query) joins the relay.
  3. Node B (NO llm/rag locally) joins — roster gossip registers A's caps on B.
  4. B routes llm.chat -> through the relay mailbox -> A serves it -> reply returns.
  5. Node C joins later; roster gossip makes A, B, and C mutually aware
     (all-to-all) without any node needing inbound reachability.

No mocks: genuine uvicorn server + httpx long-poll carry every envelope.
"""

from __future__ import annotations

import asyncio
import contextlib
import socket

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("uvicorn")
pytest.importorskip("httpx")

from hearthnet.node import HearthNode
from hearthnet.transport.relay_hub import RelayHub, mount_relay_endpoints


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def _serve_relay(port: int):
    import uvicorn
    from fastapi import FastAPI

    app = FastAPI()
    hub = RelayHub(member_ttl_seconds=60)
    mount_relay_endpoints(app, hub)

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", lifespan="off")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())

    import httpx

    deadline = asyncio.get_event_loop().time() + 5.0
    async with httpx.AsyncClient(timeout=1.0) as client:
        while asyncio.get_event_loop().time() < deadline:
            with contextlib.suppress(Exception):
                r = await client.get(f"http://127.0.0.1:{port}/relay/v1/roster")
                if r.status_code == 200:
                    break
            await asyncio.sleep(0.1)
        else:
            raise TimeoutError("relay hub never became ready")

    async def _shutdown() -> None:
        server.should_exit = True
        with contextlib.suppress(Exception):
            await task

    return hub, _shutdown


async def _wait_until(predicate, timeout: float = 6.0) -> bool:
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.05)
    return False


@pytest.mark.asyncio
async def test_all_to_all_mesh_over_relay():
    port = _free_port()
    relay_url = f"http://127.0.0.1:{port}"
    _hub, shutdown = await _serve_relay(port)

    node_a = HearthNode("ed25519:relA", "Alice", "ed25519:community")
    node_a.install_demo_services(corpus="alpha")
    node_b = HearthNode("ed25519:relB", "Bob", "ed25519:community")
    node_c = HearthNode("ed25519:relC", "Carol", "ed25519:community")

    try:
        # B has no llm/rag locally — it can only answer by routing over the mesh.
        assert "llm.chat" not in {e.descriptor.name for e in node_b.bus.registry.all_local()}

        await node_a.join_relay(relay_url)
        await node_b.join_relay(relay_url)

        # Roster gossip: B learns A's capabilities through the hub.
        assert await _wait_until(
            lambda: any(e.node_id == "ed25519:relA" for e in node_b.bus.registry.all_remote())
        ), "B never learned A via roster"

        # B routes llm.chat across the relay to A and gets the echo back.
        chat = await node_b.bus.call(
            "llm.chat",
            (1, 0),
            {"input": {"messages": [{"role": "user", "content": "hello mesh"}]}},
        )
        assert "hello mesh" in chat["output"]["message"]["content"]

        # B routes rag.query across the relay to A too.
        rag = await node_b.bus.call(
            "rag.query", (1, 0), {"input": {"query": "water"}}
        )
        assert "output" in rag

        # C joins late — all three become mutually aware (all-to-all).
        await node_c.join_relay(relay_url)
        assert await _wait_until(lambda: node_a.peers.get("ed25519:relC") is not None), (
            "A never learned late-joiner C"
        )
        assert await _wait_until(lambda: node_b.peers.get("ed25519:relC") is not None), (
            "B never learned late-joiner C"
        )
        assert node_c.peers.get("ed25519:relA") is not None
    finally:
        await node_a.leave_relay()
        await node_b.leave_relay()
        await node_c.leave_relay()
        await shutdown()


@pytest.mark.asyncio
async def test_mesh_join_capability_requires_relay():
    node = HearthNode("ed25519:solo", "Solo", "ed25519:community")
    result = await node.bus.call("mesh.join", (1, 0), {"input": {}})
    assert result.get("error") == "bad_request"


@pytest.mark.asyncio
async def test_join_exposes_hub_node_id():
    """The relay join response advertises the hub's own in-process node id.

    Clients use this id to address the hub directly over HTTP (bypassing the
    mailbox poll loop), so cross-node RPC keeps working regardless of which
    event loop the caller runs on.
    """
    import httpx

    port = _free_port()
    hub, shutdown = await _serve_relay(port)
    # The Space serves its own node "ed25519:hub" in-process.
    hub.set_local_handler("ed25519:hub", object())
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.post(
                f"http://127.0.0.1:{port}/relay/v1/join",
                json={"node_id": "ed25519:caller", "capabilities": []},
            )
            data = resp.json()
        assert data["hub_node_id"] == "ed25519:hub"
    finally:
        await shutdown()


def test_hub_peer_routed_via_direct_http_across_loops():
    """A node addressed via the hub is reachable from any event loop.

    Regression for the Gradio cross-event-loop bug: the relay poll loop starts
    in loop A (during join), but Chat handlers run on loop B. A mailbox-poll
    future bound to loop A never resolves in loop B, so delivery degraded to
    "queued". Routing the hub node over direct HTTP (learned from
    ``hub_node_id``) avoids the poll loop entirely, so a call issued on a
    *separate* event loop still delivers.
    """
    import threading
    import time

    import httpx
    from hearthnet.transport.server import HttpServer

    port = _free_port()
    relay_url = f"http://127.0.0.1:{port}"

    # The Space (hub) serves its own node in-process and answers chat.deliver,
    # and exposes its bus over HTTP at /bus/v1/call (same as the real Space).
    space = HearthNode("ed25519:spaceHub", "SpaceHub", "ed25519:community")
    space.install_demo_services(corpus="alpha")

    hub = RelayHub(member_ttl_seconds=60)
    hub.set_local_handler("ed25519:spaceHub", space.bus)
    # The Space self-joins its own hub, advertising its capabilities, so remote
    # nodes see it (with chat.deliver) in the roster (mirrors app.py auto-join).
    hub.join(
        "ed25519:spaceHub",
        display_name="SpaceHub",
        community_id="ed25519:community",
        capabilities=[
            f"{e.descriptor.name}@{e.descriptor.version[0]}.{e.descriptor.version[1]}"
            for e in space.bus.registry.all_local()
        ],
    )

    server = HttpServer(
        bus=space.bus,
        node_manifest_fn=lambda: space.manifest().as_dict(),
        host="127.0.0.1",
        port=port,
    )
    app = server.build_app()
    mount_relay_endpoints(app, hub)

    # Run the server on its own thread + event loop (mirrors uvicorn in prod).
    import uvicorn

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", lifespan="off")
    userver = uvicorn.Server(config)
    server_thread = threading.Thread(target=userver.run, daemon=True)
    server_thread.start()

    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline:
        with contextlib.suppress(Exception):
            if httpx.get(f"{relay_url}/health", timeout=1.0).status_code == 200:
                break
        time.sleep(0.1)

    client_node = HearthNode("ed25519:client", "Client", "ed25519:community")
    client_node.install_demo_services(corpus="beta")

    try:
        # Loop A: join the relay (starts the poll loop, bound to *this* loop).
        asyncio.run(client_node.join_relay(relay_url))

        # The hub node must be registered with a *direct* http endpoint, not a
        # relay endpoint.
        hub_entry = next(
            (
                e
                for e in client_node.bus.registry.all_remote()
                if e.node_id == "ed25519:spaceHub"
            ),
            None,
        )
        assert hub_entry is not None, "client never learned the hub node"
        assert hub_entry.endpoint is not None
        assert hub_entry.endpoint.transport in ("http", "https"), (
            f"hub endpoint should be direct HTTP, got {hub_entry.endpoint.transport!r}"
        )

        # Loop B (a *different* event loop): send chat to the hub node. With the
        # direct-HTTP endpoint this delivers; via the relay poll loop it would
        # time out and degrade to "queued".
        async def _send() -> dict:
            return await client_node.bus.call(
                "chat.send",
                (1, 0),
                {"input": {"to": "ed25519:spaceHub", "text": "hello hub"}},
            )

        result = asyncio.run(_send())
        assert result["output"]["delivered"] == "delivered", (
            f"expected direct-HTTP delivery, got {result['output']}"
        )
    finally:
        with contextlib.suppress(Exception):
            asyncio.run(client_node.leave_relay())
        userver.should_exit = True
        server_thread.join(timeout=5.0)
