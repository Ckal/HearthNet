"""Phase 2 functional tests — M14-M25, X05-X07.

Covers:
- M14 Federation manifests and peering
- M16 Capability tokens
- M17 OCR service (backend health, graceful unavailable)
- M18 Translation service
- M19 STT/TTS services
- M20 Vision/Image services
- M21 Tool calls (ToolExecutor)
- M23 E2E encryption (X3DH + ratchet + envelope)
- M24 Reranking service
- M25 Group chat threads
- X05 DHT Kademlia node
- X06 WebSocket pubsub
- X07 Federated metrics
- Relay client (M15)
"""
from __future__ import annotations

from hearthnet.bus.capability import RouteRequest


def _req(body: dict, cap: str = "test", caller: str = "test") -> RouteRequest:
    """Wrap a body dict as a RouteRequest for direct service handler calls."""
    return RouteRequest(
        capability=cap, version_req="1.0", body=body,
        caller=caller, trace_id="test-trace",
    )

import asyncio
import base64
import time

import nacl.signing
import pytest

from hearthnet.identity.keys import KeyPair, full_node_id, generate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_keypair() -> KeyPair:
    return generate()


# ===========================================================================
# M23 — E2E Encryption
# ===========================================================================

def test_e2e_x3dh_and_ratchet():
    """X3DH key agreement + Double Ratchet encrypt/decrypt round-trip."""
    from hearthnet.crypto.kem import (
        build_prekey_bundle,
        derive_identity_x25519_from_ed25519,
        x25519_generate,
        x3dh_initiator,
        x3dh_responder,
    )
    from hearthnet.crypto.ratchet import decrypt, encrypt, init_from_shared_secret

    kp_a = _make_keypair()
    kp_b = _make_keypair()

    bundle_b, spk_b, otp_b = build_prekey_bundle(kp_b, num_one_time=3)
    eph_a = x25519_generate()
    id_x_a = derive_identity_x25519_from_ed25519(kp_a)
    id_x_b = derive_identity_x25519_from_ed25519(kp_b)

    ss_init, init_msg = x3dh_initiator(id_x_a, eph_a, bundle_b)

    def _b64d(s: str) -> bytes:
        pad = 4 - len(s) % 4
        return base64.urlsafe_b64decode(s + "=" * (pad % 4))

    otp_used = otp_b[init_msg["used_otp_index"]] if init_msg["used_otp_index"] is not None else None
    ss_resp = x3dh_responder(
        id_x_b, spk_b, otp_used,
        _b64d(init_msg["ephemeral_pub"]),
        _b64d(init_msg["identity_pub"]),
    )
    assert ss_init == ss_resp, "X3DH shared secrets must match"

    # Double Ratchet
    s_alice = init_from_shared_secret(ss_init, is_initiator=True)
    s_bob   = init_from_shared_secret(ss_resp, is_initiator=False)

    messages = [b"hello", b"world"] + [b"test message " + str(i).encode() for i in range(5)]
    for i, msg in enumerate(messages):
        ct, hdr = encrypt(s_alice, msg)
        pt = decrypt(s_bob, ct, hdr)
        assert pt == msg, f"Message {i} decryption mismatch"


def test_e2e_envelope():
    """File chunk envelope encrypt/decrypt."""
    from hearthnet.crypto.envelope import envelope_decrypt, envelope_encrypt, per_recipient_key

    shared = b"\xab" * 32
    key = per_recipient_key(shared, "bob_node", "blake3:abc123")
    assert len(key) == 32

    plaintext = b"This is a test blob chunk."
    env = envelope_encrypt(plaintext, key)
    assert env.ciphertext != plaintext
    assert envelope_decrypt(env, key) == plaintext


def test_e2e_prekeys():
    """PrekeyStore stores, loads, and consumes one-time prekeys."""
    from hearthnet.crypto.kem import build_prekey_bundle
    from hearthnet.crypto.prekeys import PrekeyStore

    kp = _make_keypair()
    bundle, spk, otp_list = build_prekey_bundle(kp, num_one_time=4)

    store = PrekeyStore()
    store.store_bundle(bundle, spk, otp_list)

    loaded_bundle, _ = store.load_bundle()
    assert len(loaded_bundle.one_time_prekeys) == 4

    # Consume one — should succeed and then be gone
    kp_otp = store.consume_one_time_prekey(loaded_bundle.one_time_prekeys[0])
    assert kp_otp is not None
    assert store.consume_one_time_prekey(loaded_bundle.one_time_prekeys[0]) is None


# ===========================================================================
# M16 — Capability Tokens
# ===========================================================================

def test_token_issue_verify():
    """Issue a token, decode it, and verify it."""
    from hearthnet.identity.tokens import TokenScope, decode_token, issue_token, verify_token

    kp = _make_keypair()
    scope = TokenScope(capabilities=["rag.query@1.0", "embed.text@1.0"])
    tok, encoded = issue_token(kp, "some-node-id", "", scope, ttl_seconds=3600)

    assert encoded.startswith("hntoken://v1/")
    decoded = decode_token(encoded)
    assert decoded.jti == tok.jti
    assert "rag.query@1.0" in decoded.scope.capabilities

    # Should not raise
    verify_token(decoded)


def test_token_expired():
    """Verify that an expired token raises TokenError."""
    from hearthnet.identity.tokens import TokenScope, TokenError, decode_token, issue_token, verify_token

    kp = _make_keypair()
    scope = TokenScope(capabilities=["llm.chat@1.0"])
    _, encoded = issue_token(kp, "node-x", "", scope, ttl_seconds=-1)
    decoded = decode_token(encoded)

    with pytest.raises((ValueError, TokenError)):
        verify_token(decoded, now=time.time() + 100)


def test_auth_service():
    """AuthService issues and verifies tokens via bus capabilities."""
    from hearthnet.services.auth.service import AuthService

    kp = _make_keypair()
    svc = AuthService(keypair=kp)

    result = svc._handle_issue({
        "subject": "node-abc",
        "audience": "",
        "capabilities": ["rag.query@1.0"],
        "ttl_seconds": 3600,
        "issued_via": "manual",
    })
    assert "token" in result
    assert result["token"].startswith("hntoken://v1/")

    verify_result = svc._handle_verify({"token": result["token"]})
    assert verify_result["valid"] is True
    assert "rag.query@1.0" in verify_result["capabilities"]


# ===========================================================================
# M14 — Federation
# ===========================================================================

def test_federation_manifest_build():
    """Build, co-sign, and finalize a federation manifest."""
    from hearthnet.federation.manifest import (
        FederationManifest,
        FederationScope,
        build_federation_proposal,
        co_sign_federation,
        finalize_federation_manifest,
    )

    kp_a = _make_keypair()
    kp_b = _make_keypair()

    class MockManifest:
        community_id = "comm-alpha"
        community_name = "Alpha"

    scope_a = FederationScope(capabilities=["rag.query@1.0"], data_visibility="public_corpora_only")
    scope_b = FederationScope(capabilities=["embed.text@1.0"], data_visibility="members_only")

    proposal = build_federation_proposal(
        MockManifest(), kp_a,
        their_community_id="comm-beta",
        their_community_name="Beta",
        scope_we_grant=scope_a,
        scope_they_grant=scope_b,
        bootstrap_endpoints=["http://alpha:7080"],
    )
    assert proposal.community_a == "comm-alpha"
    assert proposal.community_b == "comm-beta"

    co_sig = co_sign_federation(proposal, kp_b, role="anchor_b")
    assert "signature" in co_sig

    manifest = finalize_federation_manifest(
        proposal, proposal.proposer_sig, co_sig["signature"], "Alpha", "Beta"
    )
    assert isinstance(manifest, FederationManifest)
    assert manifest.community_a_id == "comm-alpha"
    assert manifest.community_b_id == "comm-beta"
    assert not manifest.is_expired()


def test_federation_service():
    """FederationService lists empty peers at startup."""
    from hearthnet.federation.service import FederationService

    kp = _make_keypair()
    svc = FederationService(keypair=kp)
    result = svc._handle_list({})
    assert "peers" in result
    assert isinstance(result["peers"], list)


# ===========================================================================
# M17 — OCR Service
# ===========================================================================

def test_ocr_service_health():
    """OcrService initialises and reports health (backends may be unavailable)."""
    from hearthnet.services.ocr.service import OcrService

    svc = OcrService()
    # OcrService exposes backends list; check it's iterable
    assert hasattr(svc, '_backends')


@pytest.mark.asyncio
async def test_ocr_service_unavailable_graceful():
    """OCR call with no installed backends returns error dict, not exception."""
    from hearthnet.services.ocr.service import OcrService
    import inspect

    svc = OcrService(backends=[])  # no backends

    result = await svc._handle_image({
        "image_b64": base64.b64encode(b"fake image").decode(),
        "languages": ["de"],
    })
    assert "error" in result


# ===========================================================================
# M18 — Translation Service
# ===========================================================================

def test_translation_service_health():
    """TranslationService initialises cleanly."""
    from hearthnet.services.translation.service import TranslationService

    svc = TranslationService()
    assert hasattr(svc, '_backends')


@pytest.mark.asyncio
async def test_translation_too_long():
    """Text over 4000 chars returns bad_request."""
    from hearthnet.services.translation.service import TranslationService

    svc = TranslationService(backends=[])
    result = await svc._handle_translate({
        "text": "x" * 5000,
        "to_lang": "en",
    })
    assert result.get("error") == "bad_request"


# ===========================================================================
# M19 — STT / TTS Services
# ===========================================================================

def test_stt_service_health():
    from hearthnet.services.speech.stt_service import SttService
    svc = SttService()
    assert hasattr(svc, '_backends')


def test_tts_service_health():
    from hearthnet.services.speech.tts_service import TtsService
    svc = TtsService()
    assert hasattr(svc, '_backends')


# ===========================================================================
# M20 — Vision Services
# ===========================================================================

def test_image_describe_service_health():
    from hearthnet.services.image.describe_service import ImageDescribeService
    svc = ImageDescribeService()
    health = svc.health()
    assert isinstance(health, dict)


@pytest.mark.asyncio
async def test_image_generate_service_unavailable():
    from hearthnet.services.image.generate_service import ImageGenerateService
    svc = ImageGenerateService(backends=[])
    result = await svc.generate({"prompt": "a cat"})
    assert "error" in result


# ===========================================================================
# M24 — Reranking Service
# ===========================================================================

def test_rerank_service_health():
    from hearthnet.services.rerank.service import RerankService
    svc = RerankService()
    health = svc.health()
    assert isinstance(health, dict)


@pytest.mark.asyncio
async def test_rerank_too_many_docs():
    """Over RERANK_MAX_DOCS returns bad_request."""
    from hearthnet.services.rerank.service import RerankService
    from hearthnet.constants import RERANK_MAX_DOCS

    svc = RerankService(backends=[])
    docs = [{"id": str(i), "text": f"doc {i}"} for i in range(RERANK_MAX_DOCS + 1)]
    result = await svc.rerank_text(_req({"query": "test", "docs": docs}))
    assert result.get("error") == "bad_request"


# ===========================================================================
# M25 — Group Chat Threads
# ===========================================================================

@pytest.mark.asyncio
async def test_group_chat_create_and_send():
    """Create a thread and send a message."""
    from hearthnet.services.chat.thread_service import ThreadService

    svc = ThreadService(node_id="node-alice")

    # ThreadService (and other generated services) expect params under req.body["input"]
    create_result = await svc.create_thread(_req({
        "input": {"name": "Planning", "members": ["node-alice", "node-bob"], "e2e_enabled": False}
    }))
    out = create_result.get("output", create_result)
    assert "thread_id" in out
    tid = out["thread_id"]

    send_result = await svc.send_message(_req({
        "input": {"thread_id": tid, "content": "Hello group!"}
    }))
    send_out = send_result.get("output", send_result)
    assert "event_id" in send_out

    history_result = await svc.get_history(_req({"input": {"thread_id": tid}}))
    history_out = history_result.get("output", history_result)
    msgs = history_out.get("messages", [])
    assert len(msgs) == 1
    assert msgs[0]["content"] == "Hello group!"


# ===========================================================================
# X05 — DHT Kademlia
# ===========================================================================

def test_dht_kademlia_store_find():
    """KademliaNode stores and retrieves values, computes XOR distances."""
    from hearthnet.dht.kademlia import KademliaNode, DhtContact
    import hashlib, time

    node = KademliaNode(node_id="test-node-001")

    key = hashlib.sha256(b"community:alpha").digest()
    node.store(key, {"endpoint": "http://alpha:7080"}, ttl=3600)

    val = node.find_value(key)
    assert val is not None
    assert val.payload["endpoint"] == "http://alpha:7080"

    # Expire stale values (this one is not stale)
    expired = node.expire_stale()
    assert expired == 0

    # Contact routing
    contact = DhtContact(
        node_key=hashlib.sha256(b"peer-1").digest(),
        endpoint="http://peer1:7080",
        node_id="peer-1",
        last_seen=time.time(),
    )
    node.update_contact(contact)
    closest = node.find_closest(key, k=5)
    assert len(closest) <= 5


# ===========================================================================
# X06 — WebSocket PubSub
# ===========================================================================

@pytest.mark.asyncio
async def test_websocket_pubsub():
    """WebsocketPubSub delivers messages to subscribed sessions."""
    from hearthnet.transport.websocket import WebsocketPubSub

    received: list[dict] = []

    class FakeSession:
        session_id = "fake-001"
        _closed = False
        async def send_event(self, event: str, data: dict, seq=None):
            received.append({"event": event, "data": data})

    pubsub = WebsocketPubSub()
    session = FakeSession()
    pubsub.subscribe("test-topic", session)

    count = await pubsub.publish("test-topic", "chat.message", {"text": "hi"})
    assert count == 1
    assert len(received) == 1
    assert received[0]["data"]["text"] == "hi"

    pubsub.unsubscribe("test-topic", session)
    count2 = await pubsub.publish("test-topic", "chat.message", {"text": "bye"})
    assert count2 == 0


# ===========================================================================
# X07 — Federated Metrics
# ===========================================================================

def test_federated_metrics_collect():
    """FederatedMetricsExporter collects a NodeMetricsTick."""
    from hearthnet.observability.federated import FederatedMetricsExporter, MetricsAggregator

    exporter = FederatedMetricsExporter(node_id="node-metrics-test", community_id="comm-x")
    tick = exporter.collect_tick()
    assert tick.node_id == "node-metrics-test"
    assert tick.community_id == "comm-x"
    assert tick.cpu_percent >= 0
    assert tick.memory_mb > 0

    agg = MetricsAggregator(community_id="comm-x")
    agg.apply_tick(tick)

    snapshot = agg.community_snapshot()
    assert snapshot.community_id == "comm-x"
    assert snapshot.member_count >= 1

    fed_snap = agg.federated_snapshot("peer-community")
    assert "band" in fed_snap.member_count_band or fed_snap.member_count_band  # non-empty


# ===========================================================================
# M15 — Relay Client
# ===========================================================================

def test_relay_client_init():
    """RelayClient initialises without error."""
    from hearthnet.relay.client import RelayClient
    client = RelayClient(relay_url="http://relay.hearthnet.de:7080")
    assert client._relay_url == "http://relay.hearthnet.de:7080"
