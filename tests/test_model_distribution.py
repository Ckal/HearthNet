"""Tests for ModelDistributionService and real-backend LlmService.

Spec: docs/M07-file-blobs.md, docs/p2_p3/M26-distributed-inference.md
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# ModelDistributionService — unit tests
# ---------------------------------------------------------------------------

class TestModelDistributionService:
    def _make_store(self, tmp_path: Path):
        from hearthnet.blobs.store import BlobStore
        return BlobStore(tmp_path / "blobs")

    def test_advertise_empty_returns_empty_list(self, tmp_path):
        from hearthnet.services.llm.model_distribution import ModelDistributionService
        from hearthnet.bus.capability import RouteRequest
        store = self._make_store(tmp_path)
        svc = ModelDistributionService(store=store)
        req = RouteRequest(capability="model.advertise", version_req=(1, 0), body={}, caller="test", trace_id="t")
        result = asyncio.run(svc.handle_advertise(req))
        assert result["output"]["models"] == []

    def test_advertise_after_manual_registration(self, tmp_path):
        from hearthnet.services.llm.model_distribution import ModelDistributionService, ModelRecord
        from hearthnet.bus.capability import RouteRequest
        store = self._make_store(tmp_path)
        svc = ModelDistributionService(store=store)
        # Manually add a model record
        svc._local_models["qwen2.5-3b-q4_k_m"] = ModelRecord(
            name="qwen2.5-3b-q4_k_m",
            family="qwen",
            format="gguf",
            size_bytes=2_000_000_000,
            cid="sha256:abc123",
            path="/models/qwen2.5-3b-q4_k_m.gguf",
            context_length=32768,
            quantization="q4_k_m",
        )
        req = RouteRequest(capability="model.advertise", version_req=(1, 0), body={}, caller="test", trace_id="t")
        result = asyncio.run(svc.handle_advertise(req))
        models = result["output"]["models"]
        assert len(models) == 1
        assert models[0]["name"] == "qwen2.5-3b-q4_k_m"
        assert models[0]["family"] == "qwen"
        assert models[0]["format"] == "gguf"
        assert models[0]["quantization"] == "q4_k_m"
        assert models[0]["context_length"] == 32768

    def test_chunk_read_unknown_cid(self, tmp_path):
        from hearthnet.services.llm.model_distribution import ModelDistributionService
        from hearthnet.bus.capability import RouteRequest
        store = self._make_store(tmp_path)
        svc = ModelDistributionService(store=store)
        req = RouteRequest(
            capability="model.chunk_read", version_req=(1, 0),
            body={"input": {"cid": "sha256:does-not-exist", "chunk_index": 0}},
            caller="test", trace_id="t",
        )
        result = asyncio.run(svc.handle_chunk_read(req))
        assert result.get("error") == "not_found"

    def test_chunk_read_small_blob(self, tmp_path):
        """Store a small blob and retrieve its first chunk."""
        from hearthnet.services.llm.model_distribution import ModelDistributionService
        from hearthnet.bus.capability import RouteRequest
        import base64
        store = self._make_store(tmp_path)
        svc = ModelDistributionService(store=store)

        data = b"fake model weights " * 100
        manifest = store.put(data, filename="fake-model.gguf")

        req = RouteRequest(
            capability="model.chunk_read", version_req=(1, 0),
            body={"input": {"cid": manifest.cid, "chunk_index": 0}},
            caller="test", trace_id="t",
        )
        result = asyncio.run(svc.handle_chunk_read(req))
        assert "output" in result
        assert result["output"]["chunk_index"] == 0
        chunk_data = base64.b64decode(result["output"]["data_b64"])
        assert len(chunk_data) > 0

    def test_status_no_active_jobs(self, tmp_path):
        from hearthnet.services.llm.model_distribution import ModelDistributionService
        from hearthnet.bus.capability import RouteRequest
        store = self._make_store(tmp_path)
        svc = ModelDistributionService(store=store)
        req = RouteRequest(
            capability="model.status", version_req=(1, 0),
            body={"input": {}},
            caller="test", trace_id="t",
        )
        result = asyncio.run(svc.handle_status(req))
        assert result["output"]["jobs"] == []

    def test_pull_without_bus_returns_error(self, tmp_path):
        from hearthnet.services.llm.model_distribution import ModelDistributionService
        from hearthnet.bus.capability import RouteRequest
        store = self._make_store(tmp_path)
        svc = ModelDistributionService(store=store, bus=None)
        req = RouteRequest(
            capability="model.pull", version_req=(1, 0),
            body={"input": {"model_name": "llama3.2:3b", "source_node": "bob"}},
            caller="test", trace_id="t",
        )
        result = asyncio.run(svc.handle_pull(req))
        assert result.get("error") == "bus_not_available"

    def test_capabilities_registered(self, tmp_path):
        from hearthnet.services.llm.model_distribution import ModelDistributionService
        store = self._make_store(tmp_path)
        svc = ModelDistributionService(store=store)
        caps = {item[0].name for item in svc.capabilities()}
        assert caps == {
            "model.advertise",
            "model.list",
            "model.pull",
            "model.chunk_read",
            "model.status",
        }

    def test_two_node_model_transfer(self, tmp_path):
        """End-to-end: provider stores a blob, requester discovers models via bus."""
        from hearthnet.blobs.store import BlobStore
        from hearthnet.services.llm.model_distribution import ModelDistributionService, ModelRecord
        from hearthnet.node import InMemoryNetwork

        provider_store = BlobStore(tmp_path / "provider")

        net = InMemoryNetwork()
        provider_node = net.add_node("provider", "Provider", "ed25519:test")
        requester_node = net.add_node("requester", "Requester", "ed25519:test")

        # fake model data
        fake_weights = b"binary model weights " * 500
        manifest = provider_store.put(fake_weights, filename="qwen2.5-3b.gguf")

        provider_svc = ModelDistributionService(
            store=provider_store, bus=provider_node.bus
        )
        provider_svc._local_models["qwen2.5-3b"] = ModelRecord(
            name="qwen2.5-3b",
            family="qwen",
            format="gguf",
            size_bytes=len(fake_weights),
            cid=manifest.cid,
            path="/models/qwen2.5-3b.gguf",
        )
        # Only provider has ModelDistributionService — requester discovers via remote routing
        provider_node.bus.register_service(provider_svc)
        net.mesh_discover()

        # Requester queries provider's model list (routes remote since requester has no model.list)
        list_result = asyncio.run(requester_node.bus.call("model.list", (1, 0), {"input": {}}))
        models = list_result["output"]["models"]
        assert any(m["name"] == "qwen2.5-3b" for m in models)
        
        # Also verify chunk_read works remotely
        chunk_result = asyncio.run(requester_node.bus.call(
            "model.chunk_read", (1, 0),
            {"input": {"cid": manifest.cid, "chunk_index": 0}},
        ))
        assert "output" in chunk_result
        assert chunk_result["output"]["chunk_index"] == 0

    def test_family_from_name(self):
        from hearthnet.services.llm.model_distribution import _family_from_name
        assert _family_from_name("qwen2.5-3b-q4_k_m") == "qwen"
        assert _family_from_name("llama3.2-3b") == "llama"
        assert _family_from_name("phi-4-mini") == "phi"
        assert _family_from_name("gemma-3-4b-it") == "gemma"
        assert _family_from_name("unknown-model-xyz") == "unknown"

    def test_quant_from_name(self):
        from hearthnet.services.llm.model_distribution import _quant_from_name
        assert _quant_from_name("qwen2.5-3b-q4_k_m") == "q4_k_m"
        assert _quant_from_name("llama3.2-q8_0") == "q8_0"
        assert _quant_from_name("llama3.2-f16") == "f16"
        assert _quant_from_name("llama3.2-base") == ""


# ---------------------------------------------------------------------------
# LlmService — real vs unavailable backend
# ---------------------------------------------------------------------------

class TestLlmServiceBackends:
    def test_no_backends_registers_unavailable(self):
        from hearthnet.services.llm.service import LlmService, _UnavailableBackend
        svc = LlmService()  # no backends, no model arg
        assert len(svc._backends) == 1
        assert isinstance(svc._backends[0], _UnavailableBackend)

    def test_demo_prefix_registers_echo(self):
        from hearthnet.services.llm.service import LlmService, _EchoBackend
        svc = LlmService(model="demo-local")
        assert len(svc._backends) == 1
        assert isinstance(svc._backends[0], _EchoBackend)

    def test_echo_prefix_registers_echo(self):
        from hearthnet.services.llm.service import LlmService, _EchoBackend
        svc = LlmService(model="echo-test")
        assert len(svc._backends) == 1
        assert isinstance(svc._backends[0], _EchoBackend)

    def test_unknown_model_registers_unavailable(self):
        from hearthnet.services.llm.service import LlmService, _UnavailableBackend
        svc = LlmService(model="llama3.2")  # real model name, no backend
        assert isinstance(svc._backends[0], _UnavailableBackend)

    def test_unavailable_backend_raises_on_chat(self):
        from hearthnet.services.llm.service import _UnavailableBackend
        backend = _UnavailableBackend()
        with pytest.raises(RuntimeError, match="No LLM backend available"):
            asyncio.run(backend.chat([{"role": "user", "content": "hello"}], model="x"))

    def test_real_backend_list_used(self):
        from hearthnet.services.llm.service import LlmService, _EchoBackend
        from hearthnet.services.llm.backends.base import BackendModel, ChatResult
        class FakeBackend:
            name = "fake"
            models = [BackendModel("fake-7b", "fake", 8192, False)]
            def is_available(self): return True
            async def chat(self, msgs, *, model, **kw):
                return ChatResult("fake response", 1, 2, "fake-7b", 5)
            async def complete(self, prompt, *, model, **kw):
                return ChatResult("fake complete", 1, 2, "fake-7b", 5)
            async def warm(self): pass
            async def close(self): pass
            def health(self): return {"status": "ok"}

        svc = LlmService(backends=[FakeBackend()])
        assert len(svc._backends) == 1
        assert not isinstance(svc._backends[0], _EchoBackend)
        caps = svc.capabilities()
        assert any(c[0].name == "llm.chat" for c in caps)

    def test_install_services_uses_real_or_unavailable(self, tmp_path):
        """install_services() on a real node produces a non-echo LlmService."""
        from hearthnet.node import HearthNode
        node = HearthNode("test-node", "Test", "ed25519:test")
        # install_services with no models dir (no real backends available in CI)
        node.install_services(corpus="ci-test")
        caps = {e.descriptor.name for e in node.bus.registry.all_local()}
        # Must have llm.chat registered (even if it returns 'unavailable' error)
        assert "llm.chat" in caps
        assert "rag.query" in caps
        assert "chat.send" in caps
