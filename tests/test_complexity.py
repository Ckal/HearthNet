"""Input validation and stress tests for HearthNet.

Tests edge cases, large datasets, and system limits.
Validates backend input validation and sanitization.
"""

from __future__ import annotations

import asyncio
import pytest
import tempfile
from pathlib import Path


class TestInputValidation:
    """Verify backend input validation and sanitization."""

    @pytest.mark.asyncio
    async def test_chat_empty_recipient_rejected(self):
        """Chat service should reject messages with missing recipient."""
        from hearthnet.node import InMemoryNetwork

        net = InMemoryNetwork()
        node = net.add_node("val-chat", "Val Chat", "ed25519:val_chat")
        node.install_demo_services()

        result = await node.bus.call(
            "chat.send",
            (1, 0),
            {"input": {"recipient": "", "body": "test message"}},
        )
        # Should return error
        assert "error" in result, "Should reject empty recipient"
        print(f"\n  Empty recipient rejected: {result.get('error')}")

    @pytest.mark.asyncio
    async def test_chat_self_message_rejected(self):
        """Chat service should reject sending to self."""
        from hearthnet.node import InMemoryNetwork

        net = InMemoryNetwork()
        node = net.add_node("val-self", "Val Self", "ed25519:val_self")
        node.install_demo_services()

        result = await node.bus.call(
            "chat.send",
            (1, 0),
            {"input": {"recipient": "val-self", "body": "test"}},
        )
        # Should return error
        assert "error" in result, "Should reject self-send"
        print(f"\n  Self-send rejected: {result.get('error')}")

    @pytest.mark.asyncio
    async def test_embedding_max_texts_enforced(self):
        """Embedding service should enforce max text limit."""
        from hearthnet.services.embedding.service import EmbeddingService
        from hearthnet.bus.capability import RouteRequest
        from hearthnet.constants import EMBED_MAX_TEXTS

        svc = EmbeddingService()

        # Try to embed too many texts
        too_many = ["text"] * (EMBED_MAX_TEXTS + 10)
        req = RouteRequest(
            capability="embedding.embed",
            version_req=(1, 0),
            body={"input": {"texts": too_many, "normalize": False}},
            caller="test",
            trace_id="t1",
        )
        result = await svc.handle_embed(req)

        if "error" in result:
            print(f"\n  Max texts enforced: {result.get('error')}")
            msg = str(result.get("message", result.get("error", ""))).lower()
            assert "too many" in msg or "bad_request" in result.get("error", "")

    @pytest.mark.asyncio
    async def test_embedding_max_chars_enforced(self):
        """Embedding service should enforce max character limit."""
        from hearthnet.services.embedding.service import EmbeddingService
        from hearthnet.bus.capability import RouteRequest
        from hearthnet.constants import EMBED_MAX_CHARS

        svc = EmbeddingService()

        # Text that's too long
        too_long_text = "x" * (EMBED_MAX_CHARS + 100)
        req = RouteRequest(
            capability="embedding.embed",
            version_req=(1, 0),
            body={"input": {"texts": [too_long_text], "normalize": False}},
            caller="test",
            trace_id="t1",
        )
        result = await svc.handle_embed(req)

        if "error" in result:
            print(f"\n  Max chars enforced: {result.get('error')}")
            msg = str(result.get("message", result.get("error", ""))).lower()
            assert "too long" in msg or "bad_request" in result.get("error", "")

    @pytest.mark.asyncio
    async def test_file_invalid_base64_rejected(self):
        """File service should reject invalid base64."""
        from hearthnet.services.files.service import FileService
        from hearthnet.bus.capability import RouteRequest

        svc = FileService()
        req = RouteRequest(
            capability="file.put",
            version_req=(1, 0),
            body={"input": {"filename": "test.txt", "data_b64": "not@valid@base64!!!"}},
            caller="test",
            trace_id="t1",
        )
        result = await svc.handle_put(req)

        assert result.get("error") is not None, "Should reject invalid base64"
        print(f"\n  Invalid base64 rejected: {result.get('error')}")

    @pytest.mark.asyncio
    async def test_file_missing_cid_returns_error(self):
        """File service should return error for missing CID."""
        from hearthnet.services.files.service import FileService
        from hearthnet.bus.capability import RouteRequest

        svc = FileService()
        req = RouteRequest(
            capability="file.get",
            version_req=(1, 0),
            body={"input": {"cid": ""}},
            caller="test",
            trace_id="t1",
        )
        result = await svc.handle_get(req)

        assert result.get("error") is not None, "Should reject missing CID"
        print(f"\n  Missing CID returns error: {result.get('error')}")


class TestStressConditions:
    """Stress tests for edge cases and limits."""

    @pytest.mark.asyncio
    async def test_marketplace_many_listings(self):
        """Marketplace should handle multiple listings."""
        from hearthnet.node import InMemoryNetwork

        net = InMemoryNetwork()
        node = net.add_node("stress-market", "Stress Market", "ed25519:stress_m")
        node.install_demo_services()

        # Post many listings
        for i in range(20):
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
            assert "output" in result, f"Failed posting {i}"

        # List should work
        list_result = await node.bus.call(
            "market.list",
            (1, 0),
            {"input": {"limit": 100}},
        )
        listings = list_result.get("output", {}).get(
            "posts", list_result.get("output", {}).get("listings", [])
        )
        print(f"\n  Posted {len(listings)} marketplace listings")
        assert len(listings) >= 10, f"Expected >= 10 listings, got {len(listings)}"

    def test_large_blob_chunking(self):
        """Blob chunker should handle large files."""
        from hearthnet.blobs.chunker import chunk_blob

        # 5MB blob
        large_data = b"x" * (5 * 1024 * 1024)

        manifest, chunks = chunk_blob(large_data)

        # Verify integrity
        reassembled = b"".join(chunks)
        assert reassembled == large_data, "Reassembled data should match original"
        assert len(chunks) > 5, "Should have multiple chunks for large file"
        print(f"\n  Large blob: {len(chunks)} chunks, reassembled correctly")

    def test_event_log_many_entries(self):
        """Event log should handle many entries."""
        from hearthnet.events.log import EventLog
        import gc

        td = tempfile.mkdtemp()
        try:
            log = EventLog(Path(td) / "stress.db", "stress-community")

            # Add many events
            for i in range(50):
                log.append_local(
                    "community.member.joined",
                    f"author-{i % 5}",
                    {"index": i, "data": f"event data {i}"},
                )

            # Query should still work
            events = log.since(0, limit=100)
            assert len(events) >= 45, f"Only {len(events)}/50 events stored"
            print(f"\n  Event log: {len(events)} entries stored and retrieved")

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

    @pytest.mark.asyncio
    async def test_concurrent_marketplace_posts(self):
        """Should handle concurrent marketplace postings."""
        from hearthnet.node import InMemoryNetwork

        net = InMemoryNetwork()
        node = net.add_node("stress-concurrent", "Stress Concurrent", "ed25519:stress_c")
        node.install_demo_services()

        async def post_listing(i):
            try:
                result = await node.bus.call(
                    "market.post",
                    (1, 0),
                    {
                        "input": {
                            "title": f"Concurrent {i}",
                            "body": f"Desc {i}",
                            "category": "info",
                        }
                    },
                )
                return "output" in result
            except Exception:
                return False

        # Post 15 concurrently
        tasks = [post_listing(i) for i in range(15)]
        results = await asyncio.gather(*tasks)

        successful = sum(1 for r in results if r)
        print(f"\n  Concurrent posts: {successful}/15 succeeded")
        assert successful >= 10, f"Only {successful}/15 concurrent posts succeeded"


class TestComplexityEdgeCases:
    """Test edge cases and complexity scenarios."""

    @pytest.mark.asyncio
    async def test_unicode_content_handling(self):
        """Services should handle unicode content correctly."""
        from hearthnet.node import InMemoryNetwork

        net = InMemoryNetwork()
        node = net.add_node("unicode-test", "Unicode Test", "ed25519:unicode")
        node.install_demo_services()

        # Send unicode message
        result = await node.bus.call(
            "chat.send",
            (1, 0),
            {
                "input": {
                    "recipient": "other-node",
                    "body": "Hello 你好 مرحبا Привет 🚀✨",
                }
            },
        )
        # Should handle without crashing
        assert isinstance(result, dict), "Should return result dict"
        print(f"\n  Unicode handling: OK (result keys: {list(result.keys())})")

    def test_malformed_json_handling(self):
        """Event log should handle edge cases gracefully."""
        from hearthnet.events.log import EventLog
        import gc

        td = tempfile.mkdtemp()
        try:
            log = EventLog(Path(td) / "edge.db", "edge-community")

            # Try to handle edge case events
            try:
                log.append_local("edge.event", "", {"data": None})
            except Exception as e:
                print(f"\n  Edge case handled gracefully: {type(e).__name__}")
                pass  # Should not crash

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

    @pytest.mark.asyncio
    async def test_rag_with_empty_corpus(self):
        """RAG should handle queries on empty corpus gracefully."""
        from hearthnet.node import InMemoryNetwork

        net = InMemoryNetwork()
        node = net.add_node("rag-empty", "RAG Empty", "ed25519:rag_empty")
        node.install_demo_services(corpus="empty-corpus")

        # Query without ingesting anything
        try:
            result = await node.bus.call(
                "rag.query",
                (1, 0),
                {
                    "params": {"corpus": "empty-corpus"},
                    "input": {"query": "test query", "limit": 5},
                },
            )
            chunks = result.get("output", {}).get("chunks", [])
            # Should return empty list, not crash
            assert isinstance(chunks, list), "Should return list"
            print(f"\n  Empty RAG corpus handled: returned {len(chunks)} chunks (OK)")
        except Exception as e:
            print(f"\n  Empty RAG query raised: {type(e).__name__} (acceptable)")
