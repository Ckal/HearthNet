from __future__ import annotations

import asyncio
from typing import Any

from hearthnet.controller import HearthNetController
from hearthnet.node import HearthNode, InMemoryNetwork

__all__ = [
    "HearthNetController",
    "HearthNode",
    "InMemoryNetwork",
    "answer",
    "get_capabilities",
    "status",
]


def _build_demo_network() -> InMemoryNetwork:
    network = InMemoryNetwork()
    anchor = network.add_node("ed25519:anchor", "Anchor Workstation")
    hearth = network.add_node("ed25519:hearth", "Hearth Laptop")
    spark = network.add_node("ed25519:spark", "Spark Phone")
    anchor.install_demo_services(corpus="niederrhein-demo")
    hearth.install_demo_services()
    spark.install_demo_services()
    network.mesh_discover()
    return network


def get_capabilities() -> dict[str, Any]:
    network = _build_demo_network()
    anchor = network.nodes[0]
    snapshot = anchor.snapshot()
    return {
        "system_of_concern": "community-owned resilient AI assistance",
        "controller": "HearthNetController -> HearthNode",
        "facades": ["RagFacade", "ChatFacade", "MarketplaceFacade"],
        "bus": "CapabilityBus",
        "local": snapshot["topology"].capabilities_local,
        "remote": snapshot["topology"].capabilities_remote,
    }


def status() -> dict[str, Any]:
    network = _build_demo_network()
    anchor = network.nodes[0]
    snapshot = anchor.snapshot()
    return {
        "node": snapshot["node"],
        "peers": snapshot["topology"].peers,
        "emergency": snapshot["emergency"].mode,
    }


def answer(question: str) -> str:
    network = _build_demo_network()
    anchor = network.nodes[0]
    result = asyncio.run(
        anchor.bus.call(
            "rag.query",
            (1, 0),
            {
                "params": {"corpus": "niederrhein-demo"},
                "input": {"query": question, "k": 2},
            },
        )
    )
    chunks = result["output"]["chunks"]
    if not chunks:
        return "No local chunk matched. The bus stayed local and returned an auditable miss."
    source_lines = "\n".join(
        f"- {chunk['metadata']['doc_title']}: {chunk['text']}" for chunk in chunks
    )
    return (
        "HearthNet routed this through `rag.query@1.0` on the local capability bus.\n\n"
        f"Local context:\n{source_lines}\n\n"
        "Phase 1 keeps the demo deterministic while preserving the controller -> facade -> bus -> service shape."
    )
