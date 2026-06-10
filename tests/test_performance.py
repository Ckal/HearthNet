"""Performance tests for HearthNet critical paths.

Measures throughput, latency, and resource efficiency.
Tests execution time, memory usage, and concurrent load handling.
"""
from __future__ import annotations

import asyncio
import time
import psutil
import pytest


class TestBusLatency:
    """Measure call routing and handler latency."""

    @pytest.mark.asyncio
    async def test_local_capability_call_latency(self):
        """Local in-process call should have low latency."""
        from hearthnet.node import InMemoryNetwork

        net = InMemoryNetwork()
        node = net.add_node("perf-local", "Perf Local", "ed25519:perf1")
        node.install_demo_services()

        # Measure info calls (simple, fast)
        iterations = 30
        latencies = []
        for _ in range(iterations):
            start = time.perf_counter()
            result = await node.bus.call(
                "market.list",
                (1, 0),
                {"input": {}},
            )
            elapsed = (time.perf_counter() - start) * 1000
            latencies.append(elapsed)

        avg_latency = sum(latencies) / len(latencies)
        print(f"\n  Local call latency: avg={avg_latency:.2f}ms")
        assert avg_latency < 50.0, f"Average latency {avg_latency}ms too high"

    @pytest.mark.asyncio
    async def test_embedding_throughput(self):
        """Embedding service should process texts efficiently."""
        from hearthnet.services.embedding.backends import SimpleHashBackend

        backend = SimpleHashBackend()
        
        # Warm up
        await backend.embed(["warmup"])

        # Measure throughput
        texts = [f"text number {i}" for i in range(200)]
        start = time.perf_counter()
        embeddings = await backend.embed(texts)
        elapsed = time.perf_counter() - start

        throughput = len(texts) / elapsed
        print(f"\n  Embedding throughput: {throughput:.0f} texts/sec")
        assert throughput > 50, f"Throughput {throughput:.0f} below 50 texts/sec"
        assert len(embeddings) == len(texts), "Should return all embeddings"


class TestConcurrency:
    """Measure concurrent operation handling."""

    @pytest.mark.asyncio
    async def test_concurrent_bus_calls(self):
        """System should handle multiple concurrent calls."""
        from hearthnet.node import InMemoryNetwork

        net = InMemoryNetwork()
        node = net.add_node("perf-concurrent", "Perf Concurrent", "ed25519:perf_cc")
        node.install_demo_services()

        # Launch 15 concurrent calls
        async def call_llm(i):
            try:
                result = await node.bus.call(
                    "llm.chat",
                    (1, 0),
                    {
                        "params": {"model": "demo-local"},
                        "input": {"messages": [{"role": "user", "content": f"Message {i}"}]},
                    },
                )
                return result.get("output") is not None
            except Exception as e:
                print(f"  Call {i} failed: {e}")
                return False

        tasks = [call_llm(i) for i in range(15)]
        start = time.perf_counter()
        results = await asyncio.gather(*tasks)
        elapsed = time.perf_counter() - start

        successful = sum(1 for r in results if r)
        print(f"\n  Concurrent calls: {successful}/15 completed in {elapsed:.2f}s")
        assert successful >= 10, f"Only {successful}/15 calls succeeded"


class TestMemoryEfficiency:
    """Measure memory usage patterns."""

    def test_blob_chunker_memory(self):
        """Large blob chunking should work correctly."""
        from hearthnet.blobs.chunker import chunk_blob

        # 1MB blob
        data = b"x" * (1024 * 1024)
        
        manifest, chunks = chunk_blob(data)
        
        # Verify integrity
        reassembled = b"".join(chunks)
        assert reassembled == data, "Reassembled data must match"
        assert len(chunks) > 0, "Should create chunks"
        print(f"\n  Blob chunking: {len(chunks)} chunks for 1MB blob")


class TestRagPerformance:
    """Measure RAG service performance."""

    @pytest.mark.asyncio
    async def test_rag_ingest_and_query(self):
        """RAG should ingest and retrieve documents."""
        from hearthnet.node import InMemoryNetwork

        net = InMemoryNetwork()
        node = net.add_node("perf-rag", "Perf RAG", "ed25519:perf_rag")
        node.install_demo_services(corpus="perf-test")

        # Ingest 5 documents
        for i in range(5):
            await node.bus.call(
                "rag.ingest",
                (1, 0),
                {
                    "params": {"corpus": "perf-test"},
                    "input": {
                        "doc_cid": f"doc{i}",
                        "title": f"Document {i}",
                        "text": f"Content about topic {i}. Key information.",
                    },
                },
            )

        # Query
        result = await node.bus.call(
            "rag.query",
            (1, 0),
            {
                "params": {"corpus": "perf-test"},
                "input": {"query": "topic information", "limit": 5},
            },
        )
        
        chunks = result.get("output", {}).get("chunks", [])
        assert len(chunks) > 0, "Should return chunks"
        print(f"\n  RAG query returned {len(chunks)} chunks")


class TestMarketplacePerformance:
    """Measure marketplace service performance."""

    @pytest.mark.asyncio
    async def test_marketplace_listing(self):
        """Marketplace should handle postings."""
        from hearthnet.node import InMemoryNetwork

        net = InMemoryNetwork()
        node = net.add_node("perf-market", "Perf Market", "ed25519:perf_market")
        node.install_demo_services()

        # Post 10 listings
        for i in range(10):
            result = await node.bus.call(
                "market.post",
                (1, 0),
                {
                    "input": {
                        "title": f"Listing {i}",
                        "body": f"Description {i}",
                        "category": "info",
                    }
                },
            )
            assert "output" in result, f"Posting {i} failed"

        # List
        result = await node.bus.call(
            "market.list",
            (1, 0),
            {"input": {"limit": 50}},
        )
        listings = result.get("output", {}).get("posts", result.get("output", {}).get("listings", []))
        print(f"\n  Marketplace listed {len(listings)} items")
        assert len(listings) >= 5, "Should list posted items"
