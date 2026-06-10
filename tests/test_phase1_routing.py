from __future__ import annotations

import asyncio

from hearthnet.node import InMemoryNetwork


def test_routes_capability_to_discovered_remote_node() -> None:
    network = InMemoryNetwork()
    caller = network.add_node("ed25519:caller", "caller")
    provider = network.add_node("ed25519:provider", "provider")
    provider.install_demo_services()
    network.mesh_discover()

    result = asyncio.run(
        caller.bus.call(
            "rag.query",
            (1, 0),
            {"params": {"corpus": "demo"}, "input": {"query": "clean water", "k": 1}},
        )
    )

    assert result["output"]["chunks"][0]["metadata"]["doc_title"] == "Water"
    snapshot = caller.snapshot()
    assert snapshot["topology"].capabilities_remote
    assert snapshot["topology"].traces[-1].to_node == provider.node_id


def test_router_skips_quarantined_provider_and_fails_over() -> None:
    network = InMemoryNetwork()
    caller = network.add_node("ed25519:caller", "caller")
    slow = network.add_node("ed25519:slow", "slow")
    fast = network.add_node("ed25519:fast", "fast")
    slow.install_demo_services()
    fast.install_demo_services()
    network.mesh_discover()

    slow_entry = next(
        entry
        for entry in caller.bus.registry.all_remote()
        if entry.node_id == slow.node_id and entry.descriptor.name == "llm.chat"
    )
    fast_entry = next(
        entry
        for entry in caller.bus.registry.all_remote()
        if entry.node_id == fast.node_id and entry.descriptor.name == "llm.chat"
    )
    slow_entry.p50_latency_ms = 1
    fast_entry.p50_latency_ms = 100
    slow_entry.quarantined_until = 999999999.0

    result = asyncio.run(
        caller.bus.call(
            "llm.chat",
            (1, 0),
            {
                "params": {"model": "demo-local"},
                "input": {"messages": [{"role": "user", "content": "hello"}]},
            },
        )
    )

    assert result["meta"]["model"] == "demo-local"
    assert caller.snapshot()["topology"].traces[-1].to_node == fast.node_id
