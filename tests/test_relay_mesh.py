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
