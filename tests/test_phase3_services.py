"""Phase 3 research services (M30 Evidence, M31 Civil Defense) — real impls."""

from __future__ import annotations

import asyncio

from hearthnet.node import HearthNode


def _research_node() -> HearthNode:
    node = HearthNode("ed25519:research", "Research", "ed25519:test-community")
    node.install_extended_services(research=True)
    return node


def test_research_services_register_only_when_opted_in() -> None:
    plain = HearthNode("ed25519:plain", "Plain", "ed25519:test-community")
    plain.install_extended_services(research=False)
    plain_caps = {e.descriptor.name for e in plain.bus.registry.all_local()}
    assert "evidence.claim.add" not in plain_caps
    assert "civdef.alert.issue" not in plain_caps

    node = _research_node()
    caps = {e.descriptor.name for e in node.bus.registry.all_local()}
    for cap in (
        "evidence.claim.add",
        "evidence.claim.attest",
        "evidence.claim.find",
        "civdef.alert.issue",
        "civdef.alert.list",
        "civdef.audit.export",
    ):
        assert cap in caps


def test_evidence_claim_roundtrip() -> None:
    node = _research_node()

    async def _run() -> dict:
        add = await node.bus.call(
            "evidence.claim.add",
            (1, 0),
            {
                "input": {
                    "subject": "well:village-1",
                    "predicate": "water_status",
                    "object": "potable",
                }
            },
        )
        claim_id = add["output"]["claim_id"]
        await node.bus.call(
            "evidence.claim.attest", (1, 0), {"input": {"claim_id": claim_id}}
        )
        return await node.bus.call(
            "evidence.claim.find", (1, 0), {"input": {"subject": "well:village-1"}}
        )

    found = asyncio.run(_run())
    claims = found["output"]["claims"]
    assert len(claims) == 1
    assert claims[0]["object"] == "potable"
    assert claims[0]["attestations"] == 1


def test_civdef_alert_and_audit_chain() -> None:
    node = _research_node()

    async def _run() -> tuple[dict, dict]:
        await node.bus.call(
            "civdef.alert.issue",
            (1, 0),
            {
                "input": {
                    "severity": "warning",
                    "title": "Boil water notice",
                    "body": "Boil tap water before drinking.",
                    "area": "Issum, Kreis Kleve, NRW",
                }
            },
        )
        listed = await node.bus.call("civdef.alert.list", (1, 0), {"input": {}})
        audit = await node.bus.call("civdef.audit.export", (1, 0), {"input": {}})
        return listed, audit

    listed, audit = asyncio.run(_run())
    assert len(listed["output"]["alerts"]) == 1
    assert listed["output"]["alerts"][0]["title"] == "Boil water notice"
    # Tamper-evident audit chain must verify.
    assert audit["output"]["chain_valid"] is True
    assert audit["output"]["length"] >= 1
