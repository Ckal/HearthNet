from __future__ import annotations

from hearthnet.controller import HearthNetController
from hearthnet.node import InMemoryNetwork


def test_emergency_snapshot_deregisters_internet_capabilities_and_tightens_pruning() -> None:
    network = InMemoryNetwork()
    node = network.add_node("ed25519:node", "node")
    node.install_demo_services(internet_llm=True)
    controller = HearthNetController(node)

    before = controller.snapshot()
    before_caps = {cap["name"] for cap in before["topology"].capabilities_local}
    assert "llm.chat" in before_caps

    offline = controller.apply_emergency_probe(
        {"1.1.1.1": False, "8.8.8.8": False, "cloudflare.com": True, "quad9.net": True}
    )

    offline_caps = {cap["name"] for cap in offline["topology"].capabilities_local}
    assert offline["emergency"].mode == "offline"
    assert "llm.chat" not in offline_caps
    assert node.peers.prune_stale_seconds == 30

    restored = controller.apply_emergency_probe(
        {"1.1.1.1": True, "8.8.8.8": True, "cloudflare.com": True, "quad9.net": True}
    )

    restored_caps = {cap["name"] for cap in restored["topology"].capabilities_local}
    assert restored["emergency"].mode == "online"
    assert "llm.chat" in restored_caps
    assert node.peers.prune_stale_seconds == 90
