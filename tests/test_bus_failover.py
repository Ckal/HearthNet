"""Bus routing: cross-mesh failover + routing-trace observability.

Covers the gaps that made ASK/RAG appear "local only":
  * A node whose *local* provider returns an application error (e.g. the LLM
    ``_UnavailableBackend``) must fail over to a working remote provider so the
    request is answered over the mesh (internet) rather than failing.
  * Every caller-facing result is stamped with ``_routed_via`` so the UI routing
    trace can show whether a request was served locally or by a peer.
  * Inbound remote-served calls (``local_only``) must NOT fail over (no loops)
    and must NOT be stamped (the outer caller stamps the true serving node).
"""

from __future__ import annotations

import time

import pytest

from hearthnet.bus import CapabilityBus, InMemoryTransport
from hearthnet.discovery import PeerRecord
from hearthnet.services.llm.service import LlmService


def _sync_manifest(target: CapabilityBus, source: CapabilityBus) -> None:
    """Make *target* aware of *source*'s local capabilities (manifest gossip)."""
    peer = PeerRecord(
        node_id_full=source.node_id_full,
        display_name=source.node_id_full,
        community_id=source.community_id,
        endpoints=[],
        last_seen=time.monotonic(),
        source="test",
    )
    manifest = {
        "capabilities": [
            {
                "name": e.descriptor.name,
                "version": "1.0",
                "params": e.descriptor.params,
                "max_concurrent": e.descriptor.max_concurrent,
            }
            for e in source.registry.all_local()
        ]
    }
    target.registry.update_from_peer_manifest(peer, manifest)


def _two_node_mesh() -> tuple[CapabilityBus, CapabilityBus]:
    transport = InMemoryTransport()
    a = CapabilityBus(node_id_full="node-a", community_id="c", transport=transport)
    b = CapabilityBus(node_id_full="node-b", community_id="c", transport=transport)
    return a, b


@pytest.mark.asyncio
async def test_llm_fails_over_to_remote_when_local_unavailable():
    a, b = _two_node_mesh()
    a.register_service(LlmService())  # _UnavailableBackend -> returns error
    b.register_service(LlmService(model="echo-1"))  # working echo backend
    _sync_manifest(a, b)

    result = await a.call(
        "llm.chat",
        (1, 0),
        {"params": {}, "input": {"messages": [{"role": "user", "content": "hi"}]}},
    )

    assert "error" not in result
    assert result["_routed_via"] == "node-b"
    assert result["output"]["message"]["content"] == "[echo-1] hi"


@pytest.mark.asyncio
async def test_local_provider_stays_local_and_is_stamped():
    transport = InMemoryTransport()
    a = CapabilityBus(node_id_full="node-a", community_id="c", transport=transport)
    a.register_service(LlmService(model="echo-A"))

    result = await a.call(
        "llm.chat",
        (1, 0),
        {"params": {}, "input": {"messages": [{"role": "user", "content": "hi"}]}},
    )

    assert result["_routed_via"] == "local"
    assert result["output"]["message"]["content"] == "[echo-A] hi"


@pytest.mark.asyncio
async def test_no_failover_when_no_alternative_provider():
    transport = InMemoryTransport()
    a = CapabilityBus(node_id_full="node-a", community_id="c", transport=transport)
    a.register_service(LlmService())  # only an unavailable local backend

    result = await a.call(
        "llm.chat",
        (1, 0),
        {"params": {}, "input": {"messages": [{"role": "user", "content": "hi"}]}},
    )

    # No working provider anywhere -> the clear error is surfaced (not masked).
    assert "error" in result
    assert result["_routed_via"] == "local"


@pytest.mark.asyncio
async def test_inbound_remote_call_does_not_failover_or_stamp():
    a, b = _two_node_mesh()
    # B has only an unavailable backend; A has a working one.
    a.register_service(LlmService(model="echo-A"))
    b.register_service(LlmService())  # unavailable
    _sync_manifest(b, a)

    # Simulate an inbound delivery to B (as the transport does): local_only=True.
    from hearthnet.bus.capability import RouteRequest

    req = RouteRequest(
        capability="llm.chat",
        version_req=(1, 0),
        body={"params": {}, "input": {"messages": [{"role": "user", "content": "hi"}]}},
        caller="node-a",
        trace_id="t",
    )
    result = await b.handle_call(req, local_only=True)

    # B answers from its own (failing) local backend without routing back out,
    # and the inbound result is left un-stamped for the outer caller to stamp.
    assert "error" in result
    assert "_routed_via" not in result
