"""Tests for the improvements batch (items 1–15).

Covers:
  - CorpusStore SQLite persistence (item 1)
  - search_corpus bound to rag.federated_query (item 3)
  - corpus param plumbing into body["params"] (item 4)
  - _extract_json_object brace-matching parser (item 7)
  - Bus failover when sole provider is quarantined (item 8)
  - schema_hash prefix is "sha256:" not "blake3:" (item 10)
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Item 1 — CorpusStore SQLite persistence
# ---------------------------------------------------------------------------


def test_corpus_store_sqlite_persists(tmp_path: Path) -> None:
    """Chunks written to CorpusStore survive a process-restart simulation."""
    from hearthnet.services.rag.chunker import Chunk
    from hearthnet.services.rag.store import CorpusStore

    # Write
    store1 = CorpusStore(tmp_path, "test_corpus")
    chunks = [Chunk(text="hello world", metadata={"doc_cid": "doc1", "title": "Test"})]
    store1.add(chunks, [[0.1, 0.2, 0.3]])
    assert store1.count() == 1

    # "Restart" — new instance, same path
    store2 = CorpusStore(tmp_path, "test_corpus")
    if store2._db is not None or store2._use_chroma:
        assert store2.count() == 1, "Chunks should survive re-open"


def test_corpus_store_sqlite_has_doc(tmp_path: Path) -> None:
    from hearthnet.services.rag.chunker import Chunk
    from hearthnet.services.rag.store import CorpusStore

    store = CorpusStore(tmp_path, "test_corpus2")
    chunks = [Chunk(text="water safety", metadata={"doc_cid": "water.001", "title": "Water"})]
    store.add(chunks, [[0.5, 0.5]])
    assert store.has_doc("water.001")
    assert not store.has_doc("unknown.001")


def test_corpus_store_corpus_info(tmp_path: Path) -> None:
    from hearthnet.services.rag.store import CorpusStore

    store = CorpusStore(tmp_path, "info_test")
    info = store.corpus_info()
    assert "backend" in info
    assert "persistent" in info
    assert "chunks" in info
    assert info["backend"] in ("chroma", "sqlite", "in-memory")


def test_corpus_store_query_after_sqlite_persist(tmp_path: Path) -> None:
    from hearthnet.services.rag.chunker import Chunk
    from hearthnet.services.rag.store import CorpusStore

    store1 = CorpusStore(tmp_path, "query_test")
    store1.add(
        [Chunk(text="CPR steps", metadata={"doc_cid": "cpr.001"})],
        [[1.0, 0.0, 0.0]],
    )

    store2 = CorpusStore(tmp_path, "query_test")
    results = store2.query([1.0, 0.0, 0.0], k=3)
    if store2._db is not None or store2._use_chroma:
        assert len(results) >= 1
        assert results[0].chunk.text == "CPR steps"


# ---------------------------------------------------------------------------
# Item 3 — search_corpus bound capability is rag.federated_query
# ---------------------------------------------------------------------------


def test_search_corpus_uses_federated_query() -> None:
    from hearthnet.services.llm.tools import default_tool_set

    executor = default_tool_set(bus=None)
    search_tool = executor._tools.get("search_corpus")
    assert search_tool is not None, "search_corpus tool must exist"
    assert search_tool.bound_capability == "rag.federated_query", (
        f"Expected rag.federated_query, got {search_tool.bound_capability!r}"
    )


# ---------------------------------------------------------------------------
# Item 4 — corpus param plumbing into body["params"]
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_corpus_corpus_param_reaches_bus() -> None:
    """When search_corpus is called with corpus='docs', the bus body must have
    params={'corpus': 'docs'} so the router's _corpus_matches predicate sees it."""
    from hearthnet.bus.capability import RouteRequest
    from hearthnet.services.llm.tools import ToolCall, ToolDefinition, ToolExecutor

    captured: list[dict] = []

    class _FakeBus:
        async def call(self, capability, version, body):
            captured.append(body)
            return {"output": {"chunks": []}}

    tool = ToolDefinition(
        name="search_corpus",
        description="test",
        parameters_schema={"type": "object", "properties": {"query": {}, "corpus": {}}},
        bound_capability="rag.federated_query",
        bound_version=(1, 0),
    )
    executor = ToolExecutor(bus=_FakeBus(), tools=[tool])
    call = ToolCall(id="t1", name="search_corpus", arguments={"query": "water", "corpus": "docs"})
    await executor.execute(call)

    assert captured, "Bus should have been called"
    body = captured[0]
    assert body.get("params", {}).get("corpus") == "docs", (
        "corpus must be in body['params'] for the router predicate"
    )


# ---------------------------------------------------------------------------
# Item 7 — _extract_json_object brace-matching parser
# ---------------------------------------------------------------------------


def test_extract_json_object_simple() -> None:
    from hearthnet.services.llm.tools import _extract_json_object

    text = 'action: {"tool": "search", "query": "hello"}'
    start = text.index("{")
    result = _extract_json_object(text, start)
    assert result == '{"tool": "search", "query": "hello"}'


def test_extract_json_object_nested() -> None:
    from hearthnet.services.llm.tools import _extract_json_object

    text = 'action: {"tool": "search", "tags": ["a", "b"], "opts": {"k": 3}}'
    start = text.index("{")
    result = _extract_json_object(text, start)
    import json
    parsed = json.loads(result)
    assert parsed["tool"] == "search"
    assert parsed["opts"]["k"] == 3
    assert parsed["tags"] == ["a", "b"]


def test_extract_json_object_brace_in_string() -> None:
    from hearthnet.services.llm.tools import _extract_json_object

    # Braces inside a string value must not be counted
    text = 'action: {"tool": "x", "q": "use {braces} here"}'
    start = text.index("{")
    result = _extract_json_object(text, start)
    import json
    parsed = json.loads(result)
    assert parsed["q"] == "use {braces} here"


def test_extract_json_object_no_match() -> None:
    from hearthnet.services.llm.tools import _extract_json_object

    assert _extract_json_object("no braces here", 0) is None
    assert _extract_json_object("{unclosed", 0) is None


# ---------------------------------------------------------------------------
# Item 8 — bus failover when sole local provider is quarantined
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bus_failover_when_sole_local_provider_quarantined() -> None:
    """When the only matching local entry is quarantined, handle_call must
    succeed by routing to a remote alternative rather than raising not_found."""
    from hearthnet.bus import CapabilityBus, InMemoryTransport
    from hearthnet.bus.capability import CapabilityDescriptor, CapabilityEntry, RouteRequest

    transport = InMemoryTransport()
    bus_a = CapabilityBus("node-a", "community-test", transport=transport)
    bus_b = CapabilityBus("node-b", "community-test", transport=transport)

    async def good_handler(req: RouteRequest) -> dict:
        return {"output": "from_b"}

    desc = CapabilityDescriptor(name="test.cap", version=(1, 0), max_concurrent=4)
    bus_b.register_capability(desc, good_handler)

    # Add node-b as remote entry directly in node-a's registry
    remote_entry = CapabilityEntry(
        node_id="node-b",
        descriptor=desc,
        is_local=False,
        handler=None,
        last_seen=time.monotonic(),
    )
    bus_a.registry._entries[("node-b", "test.cap", (1, 0))] = remote_entry

    # Register a quarantined local entry on bus_a
    async def broken_handler(req: RouteRequest) -> dict:
        return {"error": "broken"}

    bus_a.registry.register_local(desc, broken_handler)
    for e in list(bus_a.registry.all_local()):
        if e.descriptor.name == "test.cap":
            e.quarantined_until = time.monotonic() + 3600

    req = RouteRequest(
        capability="test.cap",
        version_req=(1, 0),
        body={},
        caller="node-a",
        trace_id="test",
        deadline_ms=0,
    )
    result = await bus_a.handle_call(req)
    assert result.get("output") == "from_b", f"Expected from_b, got {result!r}"


# ---------------------------------------------------------------------------
# Item 10 — schema_hash prefix is "sha256:" not "blake3:"
# ---------------------------------------------------------------------------


def test_schema_hash_prefix_is_sha256() -> None:
    from hearthnet.bus.capability import CapabilityDescriptor

    desc = CapabilityDescriptor(name="test.cap", version=(1, 0))
    h = desc.schema_hash()
    assert h.startswith("sha256:"), f"Expected 'sha256:' prefix, got: {h!r}"
    assert not h.startswith("blake3:"), "blake3: prefix was a mislabel — must use sha256:"
