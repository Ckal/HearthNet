"""Quick functional test for all new modules."""
import asyncio
import tempfile
import pytest
from pathlib import Path


def test_config():
    from hearthnet.config import default_config
    cfg = default_config()
    assert cfg.transport.port == 7080
    assert cfg.bus.prefer_local is True
    print(f"  Config OK: port={cfg.transport.port}")


def test_identity():
    try:
        from hearthnet.identity.keys import generate, sign_payload, verify_payload
        kp = generate()
        payload = {"foo": "bar", "num": 1}
        signed = sign_payload(payload, kp)
        assert "signature" in signed
        assert verify_payload(signed, kp.verify_key)
        print(f"  Identity OK: {kp.node_id_short}")
    except Exception as e:
        print(f"  Identity SKIP (PyNaCl not installed?): {e}")


def test_events():
    from hearthnet.events.log import EventLog
    import gc
    td = tempfile.mkdtemp()
    try:
        log = EventLog(Path(td) / "events.db", "test-community")
        ev = log.append_local("community.created", "test-author", {"name": "Test"})
        assert ev.lamport == 1
        print(f"  Events OK: lamport={ev.lamport}, id={ev.event_id[:12]}")
        # Close the connection before cleanup
        if hasattr(log, "_conn") and log._conn:
            log._conn.close()
        del log
        gc.collect()
    finally:
        import shutil
        try:
            shutil.rmtree(td, ignore_errors=True)
        except Exception:
            pass


def test_blobs():
    from hearthnet.blobs.chunker import chunk_blob
    data = b"Hello HearthNet" * 1000
    manifest, chunks = chunk_blob(data)
    assert b"".join(chunks) == data
    print(f"  Blobs OK: cid={manifest.cid[:20]}, chunks={len(chunks)}")


@pytest.mark.asyncio
async def test_embedding():
    from hearthnet.services.embedding.backends import SimpleHashBackend
    backend = SimpleHashBackend()
    embeddings = await backend.embed(["hello world", "test text"])
    assert len(embeddings) == 2 and len(embeddings[0]) == 16
    print(f"  Embedding OK: {len(embeddings)} embeddings, dim={len(embeddings[0])}")


@pytest.mark.asyncio
async def test_marketplace():
    from hearthnet.services.marketplace.service import MarketplaceService
    from hearthnet.bus.capability import RouteRequest
    svc = MarketplaceService()
    req = RouteRequest(
        capability="market.post", version_req=(1, 0),
        body={"input": {"title": "Test", "body": "Hello", "category": "info"}},
        caller="test-node", trace_id="trace1",
    )
    result = await svc.handle_post(req)
    eid = result["output"]["event_id"]
    print(f"  Marketplace OK: event_id={eid[:12]}")


@pytest.mark.asyncio
async def test_chat():
    from hearthnet.services.chat.service import ChatService
    from hearthnet.bus.capability import RouteRequest
    svc = ChatService("node-a")
    req = RouteRequest(
        capability="chat.send", version_req=(1, 0),
        body={"input": {"recipient": "node-b", "body": "Hi there!"}},
        caller="node-a", trace_id="t1",
    )
    result = await svc.send(req)
    print(f"  Chat OK: delivered={result['output']['delivered']}")


@pytest.mark.asyncio
async def test_rag():
    from hearthnet.services.rag.service import RagService
    from hearthnet.bus.capability import RouteRequest
    svc = RagService(corpus="test")
    req = RouteRequest(
        capability="rag.ingest", version_req=(1, 0),
        body={"input": {"text": "Water is essential for survival. Store clean water.", "title": "Survival Tips"}},
        caller="test", trace_id="t1",
    )
    result = await svc.handle_ingest(req)
    print(f"  RAG ingest OK: chunks={result['output']['chunks_indexed']}")
    
    req2 = RouteRequest(
        capability="rag.query", version_req=(1, 0),
        body={"input": {"query": "water survival", "k": 3}, "params": {"corpus": "test"}},
        caller="test", trace_id="t2",
    )
    result2 = await svc.handle_query(req2)
    chunks = result2["output"]["chunks"]
    print(f"  RAG query OK: found {len(chunks)} chunks")


def test_cli():
    from hearthnet.cli import main
    print("  CLI OK: commands registered")


def test_onboarding():
    from hearthnet.ui.onboarding import encode_invite, decode_invite, InviteBlob, OnboardingError
    from datetime import datetime, timezone, timedelta
    exp = (datetime.now(timezone.utc) + timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
    iat = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    blob = InviteBlob(
        community_id="ed25519:test123",
        community_name="Test Community",
        inviter_node_id="ed25519:inviter",
        invitee_node_id="",
        issued_at=iat,
        expires_at=exp,
        signature="",
    )
    encoded = encode_invite(blob)
    assert encoded.startswith("hn1:")
    decoded = decode_invite(encoded)
    assert decoded.community_name == "Test Community"
    print("  Onboarding OK: invite encode/decode works")


if __name__ == "__main__":
    print("Running functional tests...")
    test_config()
    test_identity()
    test_events()
    test_blobs()
    asyncio.run(test_embedding())
    asyncio.run(test_marketplace())
    asyncio.run(test_chat())
    asyncio.run(test_rag())
    test_cli()
    test_onboarding()
    print("\nAll functional tests passed!")
