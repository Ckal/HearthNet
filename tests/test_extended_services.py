"""install_extended_services registers the real auxiliary services."""

from __future__ import annotations

import asyncio

from hearthnet.node import HearthNode


def _node() -> HearthNode:
    node = HearthNode("ed25519:ext", "Ext", "ed25519:test-community")
    node.install_extended_services(research=False)
    return node


def test_extended_services_register() -> None:
    caps = {e.descriptor.name for e in _node().bus.registry.all_local()}
    for cap in ("embed.text", "rerank.text", "ocr.image", "trans.text"):
        assert cap in caps, f"missing {cap}"


def test_embed_text_returns_vectors() -> None:
    """embed.text must return one vector per input, even without ML deps
    (SimpleHashBackend fallback) — no mock, real deterministic vectors."""
    node = _node()

    async def _run() -> dict:
        return await node.bus.call("embed.text", (1, 0), {"input": {"texts": ["hello", "world"]}})

    out = asyncio.run(_run())
    embeddings = out["output"]["embeddings"]
    assert len(embeddings) == 2
    assert all(isinstance(v, (int, float)) for v in embeddings[0])


def test_rag_query_uses_registered_embedder() -> None:
    """With embed.text registered, rag.query routes embeddings through the bus."""
    from hearthnet.services.rag.service import RagService

    node = _node()
    rag = RagService(corpus="community", bus=node.bus)
    node.bus.register_service(rag)

    async def _run() -> dict:
        await node.bus.call(
            "rag.ingest",
            (1, 0),
            {
                "input": {
                    "corpus": "community",
                    "documents": [
                        {"id": "d1", "title": "Water", "text": "Boil rainwater before drinking."}
                    ],
                }
            },
        )
        return await node.bus.call(
            "rag.query",
            (1, 0),
            {"params": {"corpus": "community"}, "input": {"query": "water", "k": 1}},
        )

    out = asyncio.run(_run())
    assert out["output"]["chunks"]
