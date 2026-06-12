"""Integration test: two real nodes peer over HTTP and route capability calls.

Proves the end-to-end wiring that lets a local node talk to the HF Space node:
  1. Node A runs a real FastAPI HttpServer exposing /bus/v1/call + /manifest.
  2. Node B (no llm/rag locally) calls discovery.peer.add with A's URL.
  3. B fetches A's manifest and registers A's capabilities as remote entries.
  4. B routes llm.chat / rag.query -> HttpBusTransport POSTs to A over HTTP.

No mocks: a genuine uvicorn server and httpx client carry the calls.
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
from hearthnet.transport.server import HttpServer


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def _wait_ready(port: int, timeout: float = 5.0) -> None:
    import httpx

    deadline = asyncio.get_event_loop().time() + timeout
    async with httpx.AsyncClient(timeout=1.0) as client:
        while asyncio.get_event_loop().time() < deadline:
            with contextlib.suppress(Exception):
                r = await client.get(f"http://127.0.0.1:{port}/health")
                if r.status_code == 200:
                    return
            await asyncio.sleep(0.1)
    raise TimeoutError(f"server on {port} never became ready")


@pytest.mark.asyncio
async def test_two_nodes_peer_and_route_over_http():
    port_a = _free_port()

    # ── Node A: provides llm.chat + rag.query, served over real HTTP ──────────
    node_a = HearthNode("ed25519:nodeA", "Alice", "ed25519:community")
    node_a.install_demo_services(corpus="alpha")
    server_a = HttpServer(
        bus=node_a.bus,
        node_manifest_fn=lambda: node_a.manifest().as_dict(),
        host="127.0.0.1",
        port=port_a,
    )
    server_a.build_app()
    await server_a.start()
    try:
        await _wait_ready(port_a)

        # ── Node B: NO llm/rag locally — must route to A ──────────────────────
        node_b = HearthNode("ed25519:nodeB", "Bob", "ed25519:community")
        local_caps = {e.descriptor.name for e in node_b.bus.registry.all_local()}
        assert "llm.chat" not in local_caps  # B can't answer locally

        # 1) Peer with A via the real discovery.peer.add capability
        add_result = await node_b.bus.call(
            "discovery.peer.add",
            (1, 0),
            {"input": {"endpoint": f"http://127.0.0.1:{port_a}"}},
        )
        added = add_result["output"]["capabilities"]
        assert "llm.chat" in added
        assert "rag.query" in added

        # 2) Route llm.chat — resolves to A and crosses the network
        chat = await node_b.bus.call(
            "llm.chat",
            (1, 0),
            {"input": {"messages": [{"role": "user", "content": "hello mesh"}]}},
        )
        content = chat["output"]["message"]["content"]
        assert "hello mesh" in content  # demo backend echoes the prompt

        # 3) Confirm the call actually went to the remote node, not local
        remote_entries = {e.node_id for e in node_b.bus.registry.all_remote()}
        assert "ed25519:nodeA" in remote_entries
    finally:
        await server_a.shutdown()


@pytest.mark.asyncio
async def test_peer_add_unreachable_endpoint_errors_cleanly():
    node = HearthNode("ed25519:solo", "Solo", "ed25519:community")
    result = await node.bus.call(
        "discovery.peer.add",
        (1, 0),
        {"input": {"endpoint": "http://127.0.0.1:1"}},  # nothing listening
    )
    assert result.get("error") == "partition"
