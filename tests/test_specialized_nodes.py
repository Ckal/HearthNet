"""Tests for specialized HearthNet node patterns.

Demonstrates and verifies:
1. OCR-only node   — registers only ocr.extract; all other calls fail-over to peers
2. Medical RAG node — registers rag.query with corpus="medical"; routes by corpus param
3. Thin client     — no local services; all bus.call() route to peers
4. Combined node   — LLM + specialized RAG corpus in one node
5. Capability matrix — verify routing picks the right node for each request type
6. Failover        — quarantined specialist node falls back to general node

All tests use in-memory transport (InMemoryNetwork). No real models, no internet.
Demo services are used explicitly (labeled FOR TESTS in node.install_demo_services()).
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

import pytest

from hearthnet.bus.capability import CapabilityDescriptor, RouteRequest
from hearthnet.node import InMemoryNetwork
from hearthnet.services.demo import (
    ChatService,
    LlmService,
    MarketplaceService,
    RagService,
)


# ---------------------------------------------------------------------------
# Minimal stub services used as stand-ins for specialized capabilities
# ---------------------------------------------------------------------------


@dataclass
class OcrService:
    """Stub for M17 OCR — registers ocr.extract@1.0.
    In production: uses Tesseract or TrOCR. Here: returns a canned result.
    """

    name: str = "ocr"
    version: str = "0.1"

    def capabilities(self) -> list[tuple[Any, ...]]:
        return [
            (
                CapabilityDescriptor(name="ocr.extract", max_concurrent=2),
                self._handle,
            )
        ]

    async def _handle(self, req: RouteRequest) -> dict[str, Any]:
        image_url = req.body.get("input", {}).get("image_url", "")
        return {
            "output": {
                "text": f"OCR result for {image_url}",
                "confidence": 0.97,
                "engine": "stub",
            }
        }


@dataclass
class TranslationService:
    """Stub for M18 Translation — registers translate.text@1.0."""

    name: str = "translation"
    version: str = "0.1"
    supported_langs: list[str] = field(default_factory=lambda: ["en", "de", "fr", "ar"])

    def capabilities(self) -> list[tuple[Any, ...]]:
        return [
            (
                CapabilityDescriptor(
                    name="translate.text",
                    params={"langs": self.supported_langs},
                    max_concurrent=4,
                ),
                self._handle,
            )
        ]

    async def _handle(self, req: RouteRequest) -> dict[str, Any]:
        inp = req.body.get("input", {})
        return {
            "output": {
                "translated": f"[{inp.get('target_lang','?')}] {inp.get('text','')}",
                "engine": "stub-nllb",
            }
        }


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def run(coro):
    return asyncio.run(coro)


# ===========================================================================
# 1. OCR-only node
# ===========================================================================


class TestOcrSpecialistNode:
    def test_ocr_node_registers_only_ocr(self):
        """An OCR node should expose ocr.extract and nothing else."""
        net = InMemoryNetwork()
        ocr_node = net.add_node("ocr-pi", "OCR-Pi", "ed25519:ocr")
        ocr_node.bus.register_service(OcrService())

        caps = [e.descriptor.name for e in ocr_node.bus.registry.all_local()]
        assert "ocr.extract" in caps
        # Should NOT have llm.chat or rag.query
        assert "llm.chat" not in caps
        assert "rag.query" not in caps

    def test_thin_client_routes_ocr_to_specialist(self):
        """A thin client with no local services routes ocr.extract to OCR node."""
        net = InMemoryNetwork()
        thin = net.add_node("thin-phone", "Phone", "ed25519:phone")
        ocr_node = net.add_node("ocr-pi", "OCR-Pi", "ed25519:ocr")
        ocr_node.bus.register_service(OcrService())
        net.mesh_discover()

        result = run(
            thin.bus.call(
                "ocr.extract",
                (1, 0),
                {"input": {"image_url": "file:///scan.jpg"}},
            )
        )
        assert "OCR result" in result["output"]["text"]
        # Verify it was routed to the specialist node
        trace = thin.snapshot()["topology"].traces
        assert trace[-1].to_node == ocr_node.node_id

    def test_ocr_node_does_not_answer_llm_calls(self):
        """An OCR-only node should raise CapabilityNotFound for llm.chat."""
        net = InMemoryNetwork()
        ocr_node = net.add_node("ocr-pi", "OCR-Pi", "ed25519:ocr")
        ocr_node.bus.register_service(OcrService())

        with pytest.raises(Exception, match="(?i)(not found|unavailable|no.*provider)"):
            run(
                ocr_node.bus.call(
                    "llm.chat",
                    (1, 0),
                    {"input": {"messages": [{"role": "user", "content": "hello"}]}},
                )
            )


# ===========================================================================
# 2. Medical RAG node (corpus-based routing)
# ===========================================================================


class TestMedicalRagNode:
    def _make_medical_node(self, net: InMemoryNetwork):
        """Create a node with a medical RAG corpus pre-seeded."""
        node = net.add_node("medical-rag", "MedRAG", "ed25519:med")
        rag = RagService(corpus="medical")
        rag.documents = [
            {
                "id": "med:001",
                "title": "Wound Care",
                "text": "Clean the wound with sterile water. Apply antiseptic. Cover with a clean bandage.",
            },
            {
                "id": "med:002",
                "title": "CPR",
                "text": "30 chest compressions at 100-120/min, then 2 rescue breaths. Repeat until help arrives.",
            },
        ]
        node.bus.register_service(rag)
        return node

    def test_medical_rag_node_answers_medical_corpus_query(self):
        """Query with corpus=medical routes to the medical RAG node."""
        net = InMemoryNetwork()
        caller = net.add_node("caller", "Caller", "ed25519:caller")
        medical_node = self._make_medical_node(net)
        net.mesh_discover()

        result = run(
            caller.bus.call(
                "rag.query",
                (1, 0),
                {"params": {"corpus": "medical"}, "input": {"query": "wound bandage", "k": 2}},
            )
        )
        chunks = result["output"]["chunks"]
        assert len(chunks) >= 1
        titles = [c["metadata"]["doc_title"] for c in chunks]
        assert "Wound Care" in titles

        # Verify routed to medical node, not caller
        trace = caller.snapshot()["topology"].traces
        assert trace[-1].to_node == medical_node.node_id

    def test_general_corpus_does_not_route_to_medical_node(self):
        """Query with corpus=community should not be answered by the medical node."""
        net = InMemoryNetwork()
        caller = net.add_node("caller", "Caller", "ed25519:caller")
        general_node = net.add_node("general", "General", "ed25519:gen")
        general_rag = RagService(corpus="community")
        general_rag.documents = [
            {"id": "c:001", "title": "Water", "text": "Boil water for 1 minute to make it safe."},
        ]
        general_node.bus.register_service(general_rag)
        self._make_medical_node(net)
        net.mesh_discover()

        result = run(
            caller.bus.call(
                "rag.query",
                (1, 0),
                {"params": {"corpus": "community"}, "input": {"query": "water", "k": 1}},
            )
        )
        chunks = result["output"]["chunks"]
        assert any("Water" in c["metadata"]["doc_title"] for c in chunks)

        trace = caller.snapshot()["topology"].traces
        assert trace[-1].to_node == general_node.node_id

    def test_two_corpora_two_nodes_route_independently(self):
        """Requests to different corpora must route to different nodes."""
        net = InMemoryNetwork()
        caller = net.add_node("caller", "Caller", "ed25519:caller")

        med_node = self._make_medical_node(net)

        law_node = net.add_node("law-rag", "LawRAG", "ed25519:law")
        law_rag = RagService(corpus="legal")
        law_rag.documents = [
            {"id": "l:001", "title": "Rights", "text": "You have the right to remain silent."}
        ]
        law_node.bus.register_service(law_rag)
        net.mesh_discover()

        med_result = run(
            caller.bus.call(
                "rag.query",
                (1, 0),
                {"params": {"corpus": "medical"}, "input": {"query": "chest compressions rescue breaths", "k": 1}},
            )
        )
        law_result = run(
            caller.bus.call(
                "rag.query",
                (1, 0),
                {"params": {"corpus": "legal"}, "input": {"query": "rights silent", "k": 1}},
            )
        )

        traces = caller.snapshot()["topology"].traces
        # Last two traces should be to different nodes
        assert traces[-2].to_node == med_node.node_id
        assert traces[-1].to_node == law_node.node_id

        assert med_result["output"]["chunks"][0]["metadata"]["doc_title"] == "CPR"
        assert law_result["output"]["chunks"][0]["metadata"]["doc_title"] == "Rights"


# ===========================================================================
# 3. Thin client
# ===========================================================================


class TestThinClient:
    def test_thin_client_has_no_local_capabilities(self):
        net = InMemoryNetwork()
        thin = net.add_node("phone", "Phone", "ed25519:ph")
        caps = list(thin.bus.registry.all_local())
        assert len(caps) == 0

    def test_thin_client_uses_peer_llm(self):
        """Thin client routes llm.chat to the LLM provider node."""
        net = InMemoryNetwork()
        thin = net.add_node("phone", "Phone", "ed25519:ph")
        llm_node = net.add_node("llm-workstation", "LLM-WS", "ed25519:llm")
        llm_node.install_demo_services()
        net.mesh_discover()

        result = run(
            thin.bus.call(
                "llm.chat",
                (1, 0),
                {
                    "params": {"model": "demo-local"},
                    "input": {"messages": [{"role": "user", "content": "hello"}]},
                },
            )
        )
        assert "hello" in result["output"]["message"]["content"].lower()
        trace = thin.snapshot()["topology"].traces
        assert trace[-1].to_node == llm_node.node_id

    def test_thin_client_uses_peer_rag(self):
        """Thin client routes rag.query to the RAG node."""
        net = InMemoryNetwork()
        thin = net.add_node("phone", "Phone", "ed25519:ph")
        rag_node = net.add_node("rag-server", "RAG", "ed25519:rag")
        rag_node.install_demo_services()
        net.mesh_discover()

        result = run(
            thin.bus.call(
                "rag.query",
                (1, 0),
                {"params": {"corpus": "demo"}, "input": {"query": "water", "k": 1}},
            )
        )
        assert result["output"]["chunks"]
        trace = thin.snapshot()["topology"].traces
        assert trace[-1].to_node == rag_node.node_id


# ===========================================================================
# 4. Combined specialized node (LLM + special corpus)
# ===========================================================================


class TestCombinedSpecialistNode:
    def test_combined_node_handles_both_llm_and_rag(self):
        """A node with LLM + specialized RAG handles both locally."""
        net = InMemoryNetwork()
        combined = net.add_node("combined", "Combined", "ed25519:combo")
        # LLM service
        combined.bus.register_service(LlmService(model="demo-local"))
        # Specialized RAG
        emergency_rag = RagService(corpus="emergency")
        emergency_rag.documents = [
            {
                "id": "e:001",
                "title": "Evacuation",
                "text": "Follow the marked evacuation route. Meet at the assembly point.",
            }
        ]
        combined.bus.register_service(emergency_rag)

        llm_caps = [e for e in combined.bus.registry.all_local() if e.descriptor.name == "llm.chat"]
        rag_caps = [e for e in combined.bus.registry.all_local() if e.descriptor.name == "rag.query"]
        assert llm_caps
        assert rag_caps

        llm_result = run(
            combined.bus.call(
                "llm.chat",
                (1, 0),
                {"params": {"model": "demo-local"}, "input": {"messages": [{"role": "user", "content": "hi"}]}},
            )
        )
        rag_result = run(
            combined.bus.call(
                "rag.query",
                (1, 0),
                {"params": {"corpus": "emergency"}, "input": {"query": "evacuation", "k": 1}},
            )
        )
        assert "hi" in llm_result["output"]["message"]["content"]
        assert "Evacuation" in rag_result["output"]["chunks"][0]["metadata"]["doc_title"]


# ===========================================================================
# 5. Capability matrix — routing picks the right node
# ===========================================================================


class TestCapabilityMatrix:
    def test_routing_matrix_four_nodes(self):
        """
        Mesh of 4 specialized nodes. Verify each request routes to the correct node.

          llm-node    → llm.chat only
          rag-node    → rag.query (corpus=community)
          ocr-node    → ocr.extract only
          trans-node  → translate.text only
          thin-client → no services (caller)
        """
        net = InMemoryNetwork()
        thin = net.add_node("thin", "Thin", "ed25519:thin")

        llm_node = net.add_node("llm", "LLM", "ed25519:llm")
        llm_node.bus.register_service(LlmService(model="demo-local"))

        rag_node = net.add_node("rag", "RAG", "ed25519:rag")
        rag_svc = RagService(corpus="community")
        rag_svc.documents = [{"id": "d1", "title": "Mesh", "text": "HearthNet is a local-first mesh."}]
        rag_node.bus.register_service(rag_svc)

        ocr_node = net.add_node("ocr", "OCR", "ed25519:ocr")
        ocr_node.bus.register_service(OcrService())

        trans_node = net.add_node("trans", "Trans", "ed25519:trans")
        trans_node.bus.register_service(TranslationService())

        net.mesh_discover()

        # LLM call → llm_node
        run(
            thin.bus.call(
                "llm.chat",
                (1, 0),
                {"params": {"model": "demo-local"}, "input": {"messages": [{"role": "user", "content": "test"}]}},
            )
        )
        assert thin.snapshot()["topology"].traces[-1].to_node == llm_node.node_id

        # RAG call → rag_node
        run(
            thin.bus.call(
                "rag.query",
                (1, 0),
                {"params": {"corpus": "community"}, "input": {"query": "mesh", "k": 1}},
            )
        )
        assert thin.snapshot()["topology"].traces[-1].to_node == rag_node.node_id

        # OCR call → ocr_node
        run(
            thin.bus.call(
                "ocr.extract",
                (1, 0),
                {"input": {"image_url": "file:///test.png"}},
            )
        )
        assert thin.snapshot()["topology"].traces[-1].to_node == ocr_node.node_id

        # Translation call → trans_node
        run(
            thin.bus.call(
                "translate.text",
                (1, 0),
                {"input": {"text": "hello", "target_lang": "de"}},
            )
        )
        assert thin.snapshot()["topology"].traces[-1].to_node == trans_node.node_id


# ===========================================================================
# 6. Local-first: node with own capability serves itself
# ===========================================================================


class TestLocalFirstRouting:
    def test_local_capability_beats_remote(self):
        """When both local and remote have llm.chat, local is used."""
        net = InMemoryNetwork()
        caller = net.add_node("caller", "Caller", "ed25519:caller")
        caller.install_demo_services()  # caller has its own llm.chat

        remote_node = net.add_node("remote", "Remote", "ed25519:remote")
        remote_node.install_demo_services()

        net.mesh_discover()

        run(
            caller.bus.call(
                "llm.chat",
                (1, 0),
                {"params": {"model": "demo-local"}, "input": {"messages": [{"role": "user", "content": "hi"}]}},
            )
        )
        traces = caller.snapshot()["topology"].traces
        # The call should be served locally (to_node == caller.node_id or None for local)
        last_trace = traces[-1]
        assert last_trace.to_node == caller.node_id or last_trace.to_node is None


# ===========================================================================
# 7. Failover: quarantined specialist falls back
# ===========================================================================


class TestSpecialistFailover:
    def test_quarantined_specialist_routes_to_backup(self):
        """
        When the specialist OCR node is quarantined, the bus should fail
        (no backup OCR provider) with an appropriate error.
        """
        net = InMemoryNetwork()
        caller = net.add_node("caller", "Caller", "ed25519:caller")
        ocr1 = net.add_node("ocr1", "OCR1", "ed25519:ocr1")
        ocr1.bus.register_service(OcrService())
        ocr2 = net.add_node("ocr2", "OCR2", "ed25519:ocr2")
        ocr2.bus.register_service(OcrService())
        net.mesh_discover()

        # Quarantine ocr1
        for entry in caller.bus.registry.all_remote():
            if entry.node_id == ocr1.node_id:
                entry.quarantined_until = 999_999_999.0

        # Should still succeed via ocr2
        result = run(
            caller.bus.call("ocr.extract", (1, 0), {"input": {"image_url": "x.jpg"}})
        )
        assert "OCR result" in result["output"]["text"]
        trace = caller.snapshot()["topology"].traces[-1]
        assert trace.to_node == ocr2.node_id

    def test_no_providers_raises_error(self):
        """With no capability providers at all, bus.call raises."""
        net = InMemoryNetwork()
        caller = net.add_node("caller", "Caller", "ed25519:caller")
        # No one registers ocr.extract

        with pytest.raises(Exception, match="not_found|not_implemented|no provider"):  # BusError — no provider
            run(caller.bus.call("ocr.extract", (1, 0), {"input": {"image_url": "x.jpg"}}))
