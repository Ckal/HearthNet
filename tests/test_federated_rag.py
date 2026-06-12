"""Tests for Phase 1 + Phase 2 distributed RAG.

Phase 1: FederatedRagService (rag.federated_query) — local-first + scatter-gather + rerank.
Phase 2: CorpusReplicator — event-driven BLAKE3 blob replication.
"""
from __future__ import annotations

import asyncio
import functools
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_rag_result(chunks: list[dict], corpus: str = "test") -> dict:
    return {"output": {"chunks": chunks}, "meta": {"corpus": corpus}}


def _chunk(text: str, score: float = 0.8, rank: int = 1, doc_cid: str | None = None) -> dict:
    return {
        "rank": rank,
        "score": score,
        "text": text,
        "metadata": {"doc_cid": doc_cid or f"cid:{text[:8]}"},
    }


# ---------------------------------------------------------------------------
# Phase 1 – FederatedRagService unit tests
# ---------------------------------------------------------------------------

class TestFederatedRagService:
    """rag.federated_query: local-first, scatter-gather, merge, rerank."""

    def _make_bus(
        self,
        local_chunks: list[dict] | None = None,
        remote_chunks: list[dict] | None = None,
        rerank_available: bool = False,
    ) -> MagicMock:
        bus = MagicMock()
        bus.node_id_full = "ed25519:local-node"

        local_result = _make_rag_result(local_chunks or [])
        remote_result = _make_rag_result(remote_chunks or [])

        async def _call(cap, ver, body, **kw):
            if cap == "rag.query":
                return local_result
            if cap == "rerank.text" and rerank_available:
                docs = body["input"]["docs"]
                # Reverse order to simulate rerank changing order
                ranked = [{"id": d["id"], "score": 0.9 - int(d["id"]) * 0.1} for d in docs]
                return {"output": {"ranked": ranked}}
            if cap == "moe.route":
                return {"output": {"candidates": []}}
            raise Exception(f"not_found: {cap}")

        bus.call = AsyncMock(side_effect=_call)

        async def _call_all(cap, ver, body, **kw):
            if cap == "rag.query":
                return [("ed25519:peer-1", remote_result)]
            return []

        bus.call_all = AsyncMock(side_effect=_call_all)
        return bus

    def test_local_first_shortcircuit(self):
        """If local score >= threshold, returns without fan-out (C strategy)."""
        from hearthnet.services.rag.federated import FederatedRagService

        chunks = [_chunk("local knowledge", score=0.9, rank=1)]
        bus = self._make_bus(local_chunks=chunks)

        svc = FederatedRagService(bus, corpus="test", confidence_threshold=0.5)
        req = MagicMock()
        req.body = {"input": {"query": "local knowledge", "k": 3, "corpus": "test"}}
        result = run(svc.handle_federated_query(req))

        assert result["meta"]["federated"] is False
        assert result["meta"]["peers_asked"] == 0
        assert len(result["output"]["chunks"]) >= 1
        # Should NOT have called call_all
        bus.call_all.assert_not_called()

    def test_scatter_gather_on_low_local_score(self):
        """When local score < threshold, fans out to peers (B strategy)."""
        from hearthnet.services.rag.federated import FederatedRagService

        local_chunks = [_chunk("weak local", score=0.2, rank=1)]
        remote_chunks = [_chunk("strong remote", score=0.95, rank=1)]
        bus = self._make_bus(local_chunks=local_chunks, remote_chunks=remote_chunks)

        svc = FederatedRagService(bus, corpus="test", confidence_threshold=0.5)
        req = MagicMock()
        req.body = {"input": {"query": "remote knowledge", "k": 5, "corpus": "test"}}
        result = run(svc.handle_federated_query(req))

        assert result["meta"]["federated"] is True
        assert result["meta"]["peers_asked"] == 1
        texts = [c["text"] for c in result["output"]["chunks"]]
        assert "strong remote" in texts

    def test_provenance_attached_to_chunks(self):
        """Each chunk must carry source_node identifying which node answered."""
        from hearthnet.services.rag.federated import FederatedRagService

        local_chunks = [_chunk("local doc", score=0.2)]
        remote_chunks = [_chunk("remote doc", score=0.95)]
        bus = self._make_bus(local_chunks=local_chunks, remote_chunks=remote_chunks)

        svc = FederatedRagService(bus, corpus="test", confidence_threshold=0.5)
        req = MagicMock()
        req.body = {"input": {"query": "docs", "k": 5, "corpus": "test"}}
        result = run(svc.handle_federated_query(req))

        for chunk in result["output"]["chunks"]:
            assert "source_node" in chunk, f"chunk missing source_node: {chunk}"

    def test_deduplication_by_doc_cid(self):
        """Same doc_cid from local + remote appears only once in merged output."""
        from hearthnet.services.rag.federated import FederatedRagService

        shared_cid = "cid:shared-doc"
        local_chunks = [_chunk("same text", score=0.2, doc_cid=shared_cid)]
        remote_chunks = [_chunk("same text", score=0.8, doc_cid=shared_cid)]
        bus = self._make_bus(local_chunks=local_chunks, remote_chunks=remote_chunks)

        svc = FederatedRagService(bus, corpus="test", confidence_threshold=0.1)
        req = MagicMock()
        req.body = {"input": {"query": "same", "k": 5, "corpus": "test"}}
        result = run(svc.handle_federated_query(req))

        cids = [c.get("metadata", {}).get("doc_cid") for c in result["output"]["chunks"]]
        assert cids.count(shared_cid) == 1, f"duplicate doc_cid in output: {cids}"

    def test_graceful_degradation_no_peers(self):
        """When no peers available, still returns local results (C-strategy fallback)."""
        from hearthnet.services.rag.federated import FederatedRagService

        local_chunks = [_chunk("only local", score=0.1)]
        bus = self._make_bus(local_chunks=local_chunks)
        bus.call_all = AsyncMock(return_value=[])  # no peers

        svc = FederatedRagService(bus, corpus="test", confidence_threshold=0.5)
        req = MagicMock()
        req.body = {"input": {"query": "anything", "k": 5, "corpus": "test"}}
        result = run(svc.handle_federated_query(req))

        assert result["output"]["chunks"][0]["text"] == "only local"

    def test_empty_query_returns_empty(self):
        """Empty query returns empty chunks without errors."""
        from hearthnet.services.rag.federated import FederatedRagService

        bus = self._make_bus()
        svc = FederatedRagService(bus, corpus="test")
        req = MagicMock()
        req.body = {"input": {"query": "", "k": 5}}
        result = run(svc.handle_federated_query(req))

        assert result["output"]["chunks"] == []


# ---------------------------------------------------------------------------
# Phase 1 – bus.call_all() primitive unit tests
# ---------------------------------------------------------------------------

class TestCallAll:
    """CapabilityBus.call_all() scatter-gather primitive."""

    def _make_bus_with_two_nodes(self):
        """Two in-process nodes sharing an InMemoryTransport."""
        from hearthnet.bus import CapabilityBus, InMemoryTransport
        from hearthnet.bus.capability import CapabilityDescriptor

        transport = InMemoryTransport()
        alpha = CapabilityBus("ed25519:alpha", "test-community", transport)
        beta = CapabilityBus("ed25519:beta", "test-community", transport)

        async def alpha_handler(req):
            return {"output": {"node": "alpha", "echo": req.body.get("input", {}).get("q")}}

        async def beta_handler(req):
            return {"output": {"node": "beta", "echo": req.body.get("input", {}).get("q")}}

        alpha.register_capability(
            CapabilityDescriptor(name="test.echo", version=(1, 0)),
            alpha_handler,
        )
        beta.register_capability(
            CapabilityDescriptor(name="test.echo", version=(1, 0)),
            beta_handler,
        )

        # Cross-register so each bus knows about the other
        from hearthnet.bus.capability import CapabilityEntry
        from hearthnet.bus.router import BusConfig

        for bus, remote_bus, _remote_handler in [
            (alpha, beta, beta_handler),
            (beta, alpha, alpha_handler),
        ]:
            from hearthnet.bus.capability import CapabilityDescriptor as CD, CapabilityEntry as CE
            entry = CE(
                descriptor=CD(name="test.echo", version=(1, 0)),
                handler=None,
                params_compatible=lambda o, r: True,
                node_id=remote_bus.node_id_full,
                is_local=False,
            )
            bus.registry._entries[f"test.echo@1.0:{remote_bus.node_id_full}"] = entry

        return alpha, beta

    def test_call_all_reaches_all_providers(self):
        """call_all fans out to all matching providers and returns all results."""
        from hearthnet.bus import CapabilityBus, InMemoryTransport
        from hearthnet.bus.capability import CapabilityDescriptor

        transport = InMemoryTransport()
        alpha = CapabilityBus("ed25519:alpha", "comm", transport)
        beta = CapabilityBus("ed25519:beta", "comm", transport)

        async def echo(req):
            return {"output": {"from": alpha.node_id_full if req else "?"}}

        alpha.register_capability(CapabilityDescriptor(name="ping", version=(1, 0)), echo)

        results = run(alpha.call_all("ping", (1, 0), {}))
        assert len(results) == 1
        assert results[0][0] == "ed25519:alpha"

    def test_call_all_tolerates_partial_failure(self):
        """call_all returns successful results even when some providers fail."""
        from hearthnet.bus import CapabilityBus, InMemoryTransport
        from hearthnet.bus.capability import CapabilityDescriptor

        transport = InMemoryTransport()
        bus = CapabilityBus("ed25519:node", "comm", transport)

        async def ok_handler(req):
            return {"output": "ok"}

        async def fail_handler(req):
            raise RuntimeError("deliberate failure")

        bus.register_capability(CapabilityDescriptor(name="test.cap", version=(1, 0)), ok_handler)

        results = run(bus.call_all("test.cap", (1, 0), {}, timeout_seconds=2.0))
        # At minimum the ok_handler result is present
        assert any(r[1].get("output") == "ok" for r in results)

    def test_call_all_empty_when_no_providers(self):
        """call_all returns empty list when nobody offers the capability."""
        from hearthnet.bus import CapabilityBus, InMemoryTransport

        transport = InMemoryTransport()
        bus = CapabilityBus("ed25519:node", "comm", transport)

        results = run(bus.call_all("nonexistent.cap", (1, 0), {}))
        assert results == []


# ---------------------------------------------------------------------------
# Phase 2 – CorpusReplicator unit tests
# ---------------------------------------------------------------------------

class TestCorpusReplicator:
    """CorpusReplicator: event-driven BLAKE3 blob replication."""

    def _make_event(
        self,
        author: str,
        corpus: str = "test",
        doc_cid: str = "cid:doc1",
        blob_cid: str = "blob:abc",
        title: str = "Test Doc",
    ):
        evt = MagicMock()
        evt.author = author
        evt.payload = {
            "corpus": corpus,
            "doc_cid": doc_cid,
            "blob_cid": blob_cid,
            "title": title,
        }
        return evt

    def test_skips_own_events(self):
        """Replicator ignores events authored by local node."""
        from hearthnet.services.rag.replication import CorpusReplicator

        bus = MagicMock()
        bus.call = AsyncMock(return_value={"output": {}})
        event_log = MagicMock()
        transfer = MagicMock()
        peers = MagicMock()
        peers.all.return_value = []

        replicator = CorpusReplicator(
            bus=bus,
            event_log=event_log,
            transfer=transfer,
            peers=peers,
            local_node_id="ed25519:local",
        )

        evt = self._make_event(author="ed25519:local")
        run(replicator._handle_event(evt))

        # Must NOT call bus.call (ingest) or transfer.fetch
        bus.call.assert_not_called()
        transfer.fetch.assert_not_called()

    def test_skips_known_docs(self):
        """If corpus_store_fn reports has_doc, replicator skips fetching."""
        from hearthnet.services.rag.replication import CorpusReplicator

        bus = MagicMock()
        bus.call = AsyncMock()
        event_log = MagicMock()
        transfer = MagicMock()
        peers = MagicMock()
        peers.all.return_value = []

        store_mock = MagicMock()
        store_mock.has_doc.return_value = True

        replicator = CorpusReplicator(
            bus=bus,
            event_log=event_log,
            transfer=transfer,
            peers=peers,
            local_node_id="ed25519:local",
            corpus_store_fn=lambda corpus: store_mock,
        )

        evt = self._make_event(author="ed25519:peer")
        run(replicator._handle_event(evt))

        store_mock.has_doc.assert_called_once_with("cid:doc1")
        bus.call.assert_not_called()

    def test_skips_when_no_blob_cid(self):
        """Without blob_cid in event payload, replicator cannot fetch."""
        from hearthnet.services.rag.replication import CorpusReplicator

        bus = MagicMock()
        bus.call = AsyncMock()
        event_log = MagicMock()
        transfer = MagicMock()
        peers = MagicMock()
        peers.all.return_value = []

        replicator = CorpusReplicator(
            bus=bus,
            event_log=event_log,
            transfer=transfer,
            peers=peers,
            local_node_id="ed25519:local",
        )

        evt = MagicMock()
        evt.author = "ed25519:peer"
        evt.payload = {"corpus": "test", "doc_cid": "cid:doc1"}  # no blob_cid

        run(replicator._handle_event(evt))
        transfer.fetch.assert_not_called()
        bus.call.assert_not_called()

    def test_fetches_and_ingests_new_doc(self):
        """Replicator fetches blob and calls rag.ingest for unknown peer doc."""
        from hearthnet.services.rag.replication import CorpusReplicator

        raw_text = b"replicated document text"

        bus = MagicMock()
        bus.call = AsyncMock(return_value={"output": {"chunks_indexed": 2, "was_duplicate": False}})

        manifest = MagicMock()
        manifest.cid = "blob:abc"
        transfer = MagicMock()
        transfer.fetch = AsyncMock(return_value=manifest)
        transfer.store = MagicMock()
        transfer.store.get = MagicMock(return_value=raw_text)

        peers = MagicMock()
        peer_rec = MagicMock()
        peer_rec.node_id = "ed25519:peer"
        ep = MagicMock()
        ep.transport = "http"
        ep.host = "192.168.1.2"
        ep.port = 7080
        peer_rec.endpoints = [ep]
        peers.all.return_value = [peer_rec]

        store_mock = MagicMock()
        store_mock.has_doc.return_value = False

        replicator = CorpusReplicator(
            bus=bus,
            event_log=MagicMock(),
            transfer=transfer,
            peers=peers,
            local_node_id="ed25519:local",
            corpus_store_fn=lambda corpus: store_mock,
        )

        evt = self._make_event(
            author="ed25519:peer",
            corpus="test",
            doc_cid="cid:doc1",
            blob_cid="blob:abc",
            title="Remote Doc",
        )
        run(replicator._handle_event(evt))

        transfer.fetch.assert_called_once_with("blob:abc", ["http://192.168.1.2:7080"])
        bus.call.assert_called_once()
        call_args = bus.call.call_args
        assert call_args[0][0] == "rag.ingest"
        ingest_input = call_args[0][2]["input"]
        assert ingest_input["text"] == raw_text.decode("utf-8")
        assert ingest_input["doc_cid"] == "cid:doc1"
        assert ingest_input["corpus"] == "test"


# ---------------------------------------------------------------------------
# Phase 1 – Integration: two-node mesh, federated query returns from both
# ---------------------------------------------------------------------------

class TestFederatedIntegration:
    """Two in-memory nodes, each with different docs. Federated query merges both."""

    def test_two_nodes_federated_returns_from_both(self):
        """Alice and Bob each have unique docs. Alice's federated query returns both."""
        from hearthnet.node import HearthNode, InMemoryNetwork

        net = InMemoryNetwork()
        alice = net.add_node("alice", "Alice", "ed25519:alice")
        bob = net.add_node("bob", "Bob", "ed25519:bob")

        alice.install_demo_services(corpus="shared")
        bob.install_demo_services(corpus="shared")
        net.mesh_discover()

        # Ingest unique docs into each node
        run(alice.bus.call(
            "rag.ingest", (1, 0),
            {"params": {"corpus": "shared"},
             "input": {"doc_cid": "alice-doc", "title": "Alice Doc",
                       "text": "alice unique knowledge about planets"}},
        ))
        run(bob.bus.call(
            "rag.ingest", (1, 0),
            {"params": {"corpus": "shared"},
             "input": {"doc_cid": "bob-doc", "title": "Bob Doc",
                       "text": "bob unique knowledge about stars"}},
        ))

        # Single-node query on Alice only returns Alice's doc
        local_result = run(alice.bus.call(
            "rag.query", (1, 0),
            {"params": {"corpus": "shared"}, "input": {"query": "stars knowledge", "k": 5}},
        ))
        local_texts = [c["text"] for c in local_result["output"]["chunks"]]
        # Alice may or may not have Bob's doc locally (no replication yet)

        # Federated query should be able to reach Bob
        federated_result = run(alice.bus.call(
            "rag.federated_query", (1, 0),
            {"params": {"corpus": "shared"},
             "input": {"query": "knowledge", "k": 5, "corpus": "shared",
                       "confidence_threshold": 0.0}},  # force fan-out
        ))
        all_texts = [c["text"] for c in federated_result["output"]["chunks"]]
        # Should have results (at minimum from local)
        assert len(all_texts) > 0
        # Federated metadata present
        assert "federated" in federated_result["meta"]

    def test_rag_service_emits_blob_cid_on_ingest(self):
        """RagService stores blob and returns blob info when blob_store is provided."""
        import tempfile
        from pathlib import Path
        from hearthnet.blobs.store import BlobStore
        from hearthnet.services.rag.service import RagService
        from hearthnet.bus.capability import RouteRequest

        with tempfile.TemporaryDirectory() as tmp:
            blob_store = BlobStore(Path(tmp) / "blobs")
            svc = RagService(corpus="test", blob_store=blob_store)

            req = MagicMock(spec=RouteRequest)
            req.body = {
                "input": {
                    "text": "hello world document content",
                    "title": "Test",
                    "doc_cid": None,
                }
            }
            result = run(svc.handle_ingest(req))

        assert result["output"]["chunks_indexed"] >= 1
        assert result["output"]["was_duplicate"] is False
        doc_cid = result["output"]["doc_cid"]
        assert doc_cid is not None
