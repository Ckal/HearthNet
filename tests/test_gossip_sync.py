"""Regression: _gossip_loop builds a working httpx adapter (not a broken HttpClient)."""

from __future__ import annotations

import asyncio
import contextlib

from hearthnet.node import _HttpxSyncClient


def test_httpx_sync_client_constructs() -> None:
    client = _HttpxSyncClient()
    # httpx is a declared dependency, so the adapter must be available.
    assert client.unavailable is False
    asyncio.run(client.aclose())


def test_sync_client_accepts_adapter() -> None:
    """SyncClient must accept the adapter without raising at construction."""
    from hearthnet.events.sync import SyncClient

    class _FakeLog:
        def head(self) -> int:
            return 0

        def since(self, _n: int):
            return []

        def append_received(self, _e) -> bool:
            return False

    adapter = _HttpxSyncClient()
    sync = SyncClient(_FakeLog(), adapter)
    assert sync is not None
    asyncio.run(adapter.aclose())


def test_gossip_loop_no_peers_is_safe() -> None:
    """A node with no peers must run the gossip loop body without raising."""
    from hearthnet.node import HearthNode

    node = HearthNode("ed25519:g", "G", "ed25519:test-community")

    class _Log:
        def head(self) -> int:
            return 0

    node._event_log = _Log()

    async def _run() -> None:
        task = asyncio.create_task(node._gossip_loop(interval=0))
        await asyncio.sleep(0.05)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    asyncio.run(_run())
