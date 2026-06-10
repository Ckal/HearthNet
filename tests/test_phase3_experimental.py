"""Phase 3 experimental module tests (M26-M31).

All Phase 3 modules are gated by config.research.* flags.
Tests verify structure, types, and graceful experimental boundaries —
NOT production correctness (these are research prototypes).
"""
from __future__ import annotations

import pytest


# ===========================================================================
# M26 — Distributed Inference
# ===========================================================================

def test_distributed_inference_plan_pipeline():
    """PipelineOrchestrator plans a pipeline from available shards."""
    from hearthnet.distributed_inference.shard import ShardDescriptor
    from hearthnet.distributed_inference.pipeline import PipelineOrchestrator

    shards = [
        ShardDescriptor("llama3:0-7",  "llama3", 0, 7,  "node-a", "http://a:7080"),
        ShardDescriptor("llama3:8-15", "llama3", 8, 15, "node-b", "http://b:7080"),
        ShardDescriptor("llama3:16-23","llama3", 16,23, "node-c", "http://c:7080"),
    ]
    orch = PipelineOrchestrator()
    pipeline = orch.plan("llama3", shards)
    assert pipeline is not None
    assert pipeline.is_complete
    assert len(pipeline.shards) == 3


def test_shard_server_not_loaded():
    from hearthnet.distributed_inference.shard import ShardDescriptor, ShardServer

    desc = ShardDescriptor("m:0-3", "model", 0, 3, "node-x", "http://x:7080")
    srv = ShardServer(desc)
    assert not srv.is_loaded()
    h = srv.health()
    assert h["loaded"] is False


@pytest.mark.asyncio
async def test_pipeline_run_raises_not_implemented():
    from hearthnet.distributed_inference.pipeline import PipelineOrchestrator

    orch = PipelineOrchestrator()
    with pytest.raises(NotImplementedError):
        await orch.run("nonexistent", [1, 2, 3])


# ===========================================================================
# M27 — MoE Expert Routing
# ===========================================================================

def test_moe_router_register_and_route():
    """MoeRouter registers experts and returns route candidates."""
    from hearthnet.moe.router import ExpertDescriptor, ExpertRegistry, MoeRouter

    registry = ExpertRegistry()
    registry.register(ExpertDescriptor(
        expert_id="model:llama3-local",
        expert_type="model",
        topic_tags=frozenset({"general", "code", "german"}),
        confidence_score=0.85,
        community_id="comm-x",
        name="Llama 3.2 3B",
    ))
    registry.register(ExpertDescriptor(
        expert_id="human:maria",
        expert_type="human",
        topic_tags=frozenset({"community", "events", "st_martins", "parade"}),
        confidence_score=1.0,
        community_id="comm-x",
        name="Maria from Issum",
    ))
    registry.register(ExpertDescriptor(
        expert_id="service:rag.query",
        expert_type="service",
        topic_tags=frozenset({"emergency", "first_aid", "local_knowledge"}),
        confidence_score=0.9,
        community_id="comm-x",
    ))

    router = MoeRouter(registry=registry)
    result = router.route("St Martins parade date", top_k=2)
    assert len(result.candidates) <= 2
    # human expert should score high for "parade"
    top_ids = [c.expert_id for c in result.candidates]
    assert any("maria" in eid for eid in top_ids)


def test_moe_handoff_lifecycle():
    from hearthnet.moe.router import ExpertRegistry, MoeRouter

    router = MoeRouter(registry=ExpertRegistry())
    handoff = router.initiate_handoff("human:hannes", "How do I fix the pump?")
    assert handoff.status == "pending"

    ok = router.resolve_handoff(handoff.handoff_id, "accepted")
    assert ok
    assert router._pending_handoffs[handoff.handoff_id].status == "accepted"


# ===========================================================================
# M28 — Federated Learning
# ===========================================================================

def test_fedlearn_create_round():
    from hearthnet.fedlearn.coordinator import FedLearnCoordinator

    coord = FedLearnCoordinator()
    manifest = coord.create_round(
        base_model_id="meta-llama/Llama-3.2-3B",
        community_id="comm-x",
        min_participants=2,
    )
    assert manifest.base_model_id == "meta-llama/Llama-3.2-3B"
    status = coord.round_status(manifest.round_id)
    assert status["participants"] == 0
    assert not status["ready_to_aggregate"]


def test_fedlearn_aggregate_raises_not_implemented():
    from hearthnet.fedlearn.coordinator import FedLearnCoordinator, ParticipantSubmission

    coord = FedLearnCoordinator()
    m = coord.create_round("model", "comm-x", min_participants=1)
    coord.submit(ParticipantSubmission(
        round_id=m.round_id,
        participant_node_id="node-1",
        delta_bytes=b"\x00" * 16,
        num_samples=100,
    ))
    with pytest.raises(NotImplementedError):
        coord.aggregate(m.round_id)


# ===========================================================================
# M29 — LoRa Beacons
# ===========================================================================

def test_lora_beacon_encode_decode():
    from hearthnet.lora.service import encode_beacon_frame, decode_beacon_frame

    frame = encode_beacon_frame("ed25519:abc123def456", sequence=42, flags=0x01)
    assert len(frame) == 32

    beacon = decode_beacon_frame(frame, device_id="sx1276-001")
    assert beacon is not None
    assert beacon.sequence == 42
    assert beacon.is_emergency
    assert not beacon.is_panic


def test_lora_service_simulated():
    from hearthnet.lora.service import LoraBeaconService

    svc = LoraBeaconService(serial_port=None, node_id_full="ed25519:testnode")
    frame = svc.send_heartbeat(flags=0)
    assert len(frame) == 32

    # Receive a beacon back
    beacon = svc.receive_frame(frame)
    assert beacon is not None
    recent = svc.recent_beacons(window_seconds=300)
    assert len(recent) == 1

    h = svc.health()
    assert h["hardware"] == "simulated"
    assert h["sent"] == 1


# ===========================================================================
# M30 — Evidence Graph
# ===========================================================================

def test_evidence_store_add_and_attest():
    from hearthnet.evidence.store import Attestation, Claim, ClaimSource, ClaimStore, SourceID

    store = ClaimStore()
    source = ClaimSource(
        source_id=SourceID("src-1"),
        source_type="ebkh",
        url="https://ebkh.example/record/42",
    )
    claim = Claim(
        claim_id="temp",   # will be overridden by content_id()
        subject="Sankt-Martins-Zug 2026",
        predicate="scheduled_for",
        object_="2026-11-11T17:00",
        asserted_by="node-christof",
        sources=(source,),
        community_id="comm-issum",
    )
    cid = store.add_claim(claim)
    assert store.get_claim(cid) is not None

    # Same claim is idempotent
    cid2 = store.add_claim(claim)
    assert cid == cid2

    store.attest(Attestation(claim_id=cid, attested_by="node-jana"))
    assert store.attestation_count(cid) == 1
    assert not store.is_disputed(cid)

    summary = store.summary()
    assert summary["claims"] == 1
    assert summary["attestations"] == 1


def test_evidence_ebkh_import():
    from hearthnet.evidence.store import ClaimStore

    store = ClaimStore()
    cid = store.import_ebkh_record(
        record={
            "ebkh_id": "ebkh-001",
            "subject": "Issum Rathaus",
            "predicate": "address",
            "object": "Rathausplatz 1, 47661 Issum",
            "source_url": "https://osm.org/node/12345",
        },
        asserted_by="node-system",
        community_id="comm-issum",
    )
    claim = store.get_claim(cid)
    assert claim is not None
    assert claim.subject == "Issum Rathaus"


# ===========================================================================
# M31 — Civil Defense
# ===========================================================================


# ===========================================================================
# MoeService — bus-registered MoE routing (moe.route / moe.register / moe.list)
# ===========================================================================

@pytest.mark.asyncio
async def test_moe_service_register_and_route():
    """MoeService registers experts via bus and routes queries."""
    from hearthnet.node import HearthNode

    node = HearthNode("moe-test", "MoE Test", "ed25519:demo")
    node.install_demo_services()

    # Register an expert
    reg = await node.bus.call("moe.register", (1, 0), {
        "input": {
            "expert_id": "model:llama-local",
            "expert_type": "model",
            "topic_tags": ["first_aid", "emergency", "medical"],
            "confidence_score": 0.88,
            "community_id": "ed25519:demo",
            "name": "Local LLM",
            "ttl_seconds": 3600,
        }
    })
    assert reg["output"]["registered"] is True
    assert reg["output"]["active_count"] == 1

    # Route a query — should return the registered expert
    result = await node.bus.call("moe.route", (1, 0), {
        "input": {"query": "emergency first aid bleeding", "top_k": 3}
    })
    candidates = result["output"]["candidates"]
    assert len(candidates) >= 1
    assert candidates[0]["expert_id"] == "model:llama-local"
    assert candidates[0]["score"] > 0


@pytest.mark.asyncio
async def test_moe_service_list_experts():
    """moe.list returns all registered experts."""
    from hearthnet.node import HearthNode

    node = HearthNode("moe-list-test", "MoE List", "ed25519:demo")
    node.install_demo_services()

    # Register two experts
    for i in range(2):
        await node.bus.call("moe.register", (1, 0), {
            "input": {
                "expert_id": f"model:expert-{i}",
                "expert_type": "model",
                "topic_tags": [f"topic_{i}"],
                "confidence_score": 0.7,
                "community_id": "ed25519:demo",
            }
        })

    result = await node.bus.call("moe.list", (1, 0), {"input": {}})
    assert result["output"]["total"] == 2


@pytest.mark.asyncio
async def test_moe_service_handoff():
    """moe.handoff creates a pending handoff to a human expert."""
    from hearthnet.node import HearthNode

    node = HearthNode("moe-handoff-test", "MoE Handoff", "ed25519:demo")
    node.install_demo_services()

    result = await node.bus.call("moe.handoff", (1, 0), {
        "input": {
            "expert_id": "human:eva",
            "query": "How do I repair the water pump?",
            "thread_id": "thread-123",
        }
    })
    assert result["output"]["status"] == "pending"
    assert result["output"]["expert_id"] == "human:eva"
    assert "handoff_id" in result["output"]


@pytest.mark.asyncio
async def test_moe_service_route_empty_registry():
    """moe.route on empty registry returns empty candidates (not an error)."""
    from hearthnet.node import HearthNode

    node = HearthNode("moe-empty-test", "MoE Empty", "ed25519:demo")
    node.install_demo_services()

    result = await node.bus.call("moe.route", (1, 0), {
        "input": {"query": "anything"}
    })
    assert "output" in result
    assert isinstance(result["output"]["candidates"], list)


# ===========================================================================
# PlantIdentificationService — tool.plant_identify
# ===========================================================================

@pytest.mark.asyncio
async def test_plant_identify_no_image_returns_error():
    """tool.plant_identify without image_b64 returns bad_request."""
    from hearthnet.node import HearthNode

    node = HearthNode("plant-test", "Plant Test", "ed25519:demo")
    node.install_demo_services()

    result = await node.bus.call("tool.plant_identify", (1, 0), {
        "input": {}
    })
    assert result.get("error") == "bad_request"


@pytest.mark.asyncio
async def test_plant_identify_invalid_base64_returns_error():
    """tool.plant_identify with invalid base64 returns bad_request."""
    from hearthnet.node import HearthNode

    node = HearthNode("plant-b64-test", "Plant b64 Test", "ed25519:demo")
    node.install_demo_services()

    result = await node.bus.call("tool.plant_identify", (1, 0), {
        "input": {"image_b64": "not-valid-base64!!"}
    })
    assert result.get("error") == "bad_request"


@pytest.mark.asyncio
async def test_plant_identify_no_vision_backend_returns_unavailable():
    """With no vision.describe registered, plant_identify returns unavailable response."""
    import base64
    from hearthnet.node import HearthNode

    node = HearthNode("plant-unavail-test", "Plant Unavail", "ed25519:demo")
    node.install_demo_services()

    # Encode 1x1 white JPEG (minimal valid image)
    tiny_jpeg = bytes([
        0xff, 0xd8, 0xff, 0xe0, 0x00, 0x10, 0x4a, 0x46, 0x49, 0x46, 0x00, 0x01,
        0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0xff, 0xdb, 0x00, 0x43,
        0x00, 0x08, 0x06, 0x06, 0x07, 0x06, 0x05, 0x08, 0x07, 0x07, 0x07, 0x09,
        0x09, 0x08, 0x0a, 0x0c, 0x14, 0x0d, 0x0c, 0x0b, 0x0b, 0x0c, 0x19, 0x12,
        0x13, 0x0f, 0x14, 0x1d, 0x1a, 0x1f, 0x1e, 0x1d, 0x1a, 0x1c, 0x1c, 0x20,
        0x24, 0x2e, 0x27, 0x20, 0x22, 0x2c, 0x23, 0x1c, 0x1c, 0x28, 0x37, 0x29,
        0x2c, 0x30, 0x31, 0x34, 0x34, 0x34, 0x1f, 0x27, 0x39, 0x3d, 0x38, 0x32,
        0x3c, 0x2e, 0x33, 0x34, 0x32, 0xff, 0xc0, 0x00, 0x0b, 0x08, 0x00, 0x01,
        0x00, 0x01, 0x01, 0x01, 0x11, 0x00, 0xff, 0xc4, 0x00, 0x1f, 0x00, 0x00,
        0x01, 0x05, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
        0x09, 0x0a, 0x0b, 0xff, 0xc4, 0x00, 0xb5, 0x10, 0x00, 0x02, 0x01, 0x03,
        0x03, 0x02, 0x04, 0x03, 0x05, 0x05, 0x04, 0x04, 0x00, 0x00, 0x01, 0x7d,
        0xff, 0xda, 0x00, 0x08, 0x01, 0x01, 0x00, 0x00, 0x3f, 0x00, 0xfb, 0xd2,
        0x8a, 0x28, 0x03, 0xff, 0xd9,
    ])
    img_b64 = base64.b64encode(tiny_jpeg).decode()

    result = await node.bus.call("tool.plant_identify", (1, 0), {
        "input": {"image_b64": img_b64, "hints": ["test"]}
    })
    # Should succeed (return unavailable response), not raise an error
    assert "output" in result
    output = result["output"]
    assert "backend_used" in output
    assert output["backend_used"] == "unavailable"
    assert "name" in output


# ===========================================================================
# ModelDistributionService — model.list / model.advertise / model.status
# ===========================================================================

@pytest.mark.asyncio
async def test_model_distribution_list_via_bus():
    """model.list returns list of models (may be empty on fresh node)."""
    from hearthnet.node import HearthNode

    node = HearthNode("model-dist-test", "Model Dist Test", "ed25519:demo")
    node.install_demo_services()

    result = await node.bus.call("model.list", (1, 0), {"input": {}})
    assert "output" in result
    assert "models" in result["output"]
    assert isinstance(result["output"]["models"], list)


@pytest.mark.asyncio
async def test_model_distribution_status_no_job():
    """model.status with no job_id returns jobs list (empty)."""
    from hearthnet.node import HearthNode

    node = HearthNode("model-status-test", "Model Status Test", "ed25519:demo")
    node.install_demo_services()

    result = await node.bus.call("model.status", (1, 0), {
        "input": {}
    })
    assert "output" in result
    assert "jobs" in result["output"]
    assert result["output"]["jobs"] == []


def test_civil_defense_issue_alert():
    from hearthnet.civdef.service import AlertSeverity, CivilDefenseService

    svc = CivilDefenseService()
    alert = svc.issue_alert(
        severity=AlertSeverity.WARNING,
        title="Hochwasserwarnung",
        body="Der Rhein steigt. Evakuieren Sie Niederrhein-Gebiete unter 30m ü.N.N.",
        area="Issum, Kreis Kleve, NRW",
        community_id="comm-issum",
        expires_in_hours=6,
    )
    assert alert.severity == "warning"
    active = svc.list_active_alerts()
    assert len(active) == 1
    assert active[0].alert_id == alert.alert_id


def test_civil_defense_audit_chain():
    from hearthnet.civdef.service import AlertSeverity, CivilDefenseService

    svc = CivilDefenseService()
    svc.issue_alert("information", "Test", "Test body", "NRW", community_id="x")
    svc.issue_alert("warning", "Flood", "Rising water", "Issum", community_id="x")

    audit = svc.export_audit()
    assert audit["chain_valid"] is True
    assert audit["length"] == 2


def test_civil_defense_role_cert():
    from hearthnet.civdef.service import CivilDefenseService, RoleCertificate

    svc = CivilDefenseService()
    cert = RoleCertificate(
        cert_id="cert-001",
        role_key="thw_helferin",
        role_label="THW Helferin",
        holder_node_id="node-franz",
        issuer_node_id="node-thw-kreisverband",
        community_id="comm-issum",
    )
    svc.register_cert(cert)
    result = svc.verify_cert("cert-001")
    assert result["valid"] is True
    assert result["role"] == "THW Helferin/Helfer"

    not_found = svc.verify_cert("cert-999")
    assert not_found["valid"] is False


# ===========================================================================
# Config — ResearchConfig
# ===========================================================================

def test_research_config_defaults():
    from hearthnet.config import default_config

    cfg = default_config()
    assert hasattr(cfg, "research")
    assert cfg.research.enable is False
    assert cfg.research.distributed_inference is False
    assert cfg.research.federated_learning is False
    assert cfg.research.civil_defense is False
