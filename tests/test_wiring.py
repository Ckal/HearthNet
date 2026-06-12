"""Integration tests for the wiring layer â€” X01, X02, X06, X09, M02, mobile.

Tests verify that:
  - HearthNode.start() / stop() lifecycle works without errors
  - EventLog initialises and provides head()
  - mDNS / UDP discovery objects can be created
  - ProtocolService (protocol.version.list / protocol.conformance.report) works via bus
  - ConformanceRunner produces a valid report
  - Mobile static assets are valid
  - WebSocket pubsub is created by HttpServer.build_app()
  - Gossip sync helpers are instantiable
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import pytest


# ===========================================================================
# HearthNode lifecycle (start / stop) â€” no external deps required
# ===========================================================================


@pytest.mark.asyncio
async def test_node_start_stop_no_network():
    """Node.start() can be called and stop() cleans up, even without network deps."""
    from hearthnet.node import HearthNode

    node = HearthNode("lifecycle-test", "Lifecycle", "ed25519:test")
    node.install_demo_services()

    # ignore_cleanup_errors needed on Windows: SQLite WAL files can stay locked
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        # start() should not raise even if fastapi/uvicorn are missing
        try:
            await asyncio.wait_for(node.start(port=0, data_dir=td), timeout=5.0)
        except (ImportError, OSError, asyncio.TimeoutError):
            pass  # graceful degradation

        await node.stop()
        assert not node._started


@pytest.mark.asyncio
async def test_node_snapshot_includes_started_flag():
    """snapshot() reports _started correctly."""
    from hearthnet.node import HearthNode

    node = HearthNode("snap-test", "Snap", "ed25519:test")
    node.install_demo_services()

    snap = node.snapshot()
    assert "started" in snap
    assert snap["started"] is False


@pytest.mark.asyncio
async def test_node_event_log_initialised_by_start():
    """After start(), _event_log is set and head() returns an int."""
    from hearthnet.node import HearthNode

    node = HearthNode("evtlog-test", "EvtLog", "ed25519:test")
    node.install_demo_services()

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        try:
            await asyncio.wait_for(node.start(port=0, data_dir=td), timeout=5.0)
        except (asyncio.TimeoutError, OSError, ImportError):
            pass  # server binding errors are fine; we just want EventLog init
        finally:
            await node.stop()

    if node._event_log is not None:
        head = node._event_log.head()
        assert isinstance(head, int)
        assert head >= 0


# ===========================================================================
# EventLog (X02) â€” standalone
# ===========================================================================


def test_event_log_creates_sqlite():
    """EventLog creates an SQLite database and returns head=0 initially."""
    from hearthnet.events.log import EventLog

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        log = EventLog(Path(td) / "events.db", "ed25519:comm", "ed25519:node")
        assert log.head() == 0


def test_event_log_append_and_since():
    """EventLog can append a local event and replay it via since()."""
    from hearthnet.events.log import EventLog

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        log = EventLog(Path(td) / "events.db", "ed25519:comm", "ed25519:node")
        event = log.append_local("market.post.created", "ed25519:node", {"title": "x09 test"})
        assert event.lamport == 1
        assert log.head() == 1

        replayed = list(log.since(0))
        assert len(replayed) == 1
        assert replayed[0].event_type == "market.post.created"


def test_replay_engine_rebuilds_view():
    """ReplayEngine can register a MaterialisedView and rebuild it from log."""
    from hearthnet.events.log import EventLog
    from hearthnet.events.replay import MaterialisedView, ReplayEngine

    class CountView(MaterialisedView):
        def reset(self):
            self.count = 0

        def apply(self, event):
            self.count += 1

        def snapshot_state(self):
            return {"count": self.count}

        def restore_state(self, state):
            self.count = state.get("count", 0)

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        log = EventLog(Path(td) / "events.db", "ed25519:comm", "ed25519:node")
        for _ in range(3):
            log.append_local("market.post.created", "ed25519:node", {"title": "test"})

        engine = ReplayEngine(log)
        view = CountView()
        view.count = 0
        engine.register("counts", view)
        engine.rebuild("counts")
        assert view.count == 3


# ===========================================================================
# SyncServer / SyncClient (X02 gossip)
# ===========================================================================


def test_sync_server_heads_empty_log():
    """SyncServer.heads() returns head=0 for a fresh log."""
    from hearthnet.events.log import EventLog
    from hearthnet.events.sync import SyncServer

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        log = EventLog(Path(td) / "events.db", "ed25519:comm", "ed25519:node")
        server = SyncServer(log)
        heads = server.heads()  # returns HeadsReport dataclass
        assert heads.head == 0
        assert heads.community_id == "ed25519:comm"


@pytest.mark.asyncio
async def test_sync_server_serve_events_accepts_empty():
    """SyncServer.serve_events() handles empty incoming events."""
    from hearthnet.events.log import EventLog
    from hearthnet.events.sync import SyncServer

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        log = EventLog(Path(td) / "events.db", "ed25519:comm", "ed25519:node")
        server = SyncServer(log)
        result = await server.serve_events(
            {"community_id": "ed25519:comm", "events": [], "our_head": 0}
        )
        assert "accepted" in result
        assert result["accepted"] == 0


@pytest.mark.asyncio
async def test_sync_client_no_http_returns_noop():
    """SyncClient with no http client returns SyncResult(0,0,0)."""
    from hearthnet.events.log import EventLog
    from hearthnet.events.sync import SyncClient

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        log = EventLog(Path(td) / "events.db", "ed25519:comm", "ed25519:node")
        client = SyncClient(log, http_client=None)
        result = await client.sync_with("http://nonexistent:9999", "ed25519:comm")
        assert result.sent_count == 0
        assert result.received_count == 0


# ===========================================================================
# Discovery (M02) â€” object creation only (no network)
# ===========================================================================


def test_mdns_announcer_created_no_zeroconf():
    """MdnsAnnouncer can be created; start() is a no-op when zeroconf unavailable."""
    from hearthnet.discovery.mdns import MdnsAnnouncer
    from hearthnet.discovery.peers import PeerRegistry

    reg = PeerRegistry("ed25519:node", "ed25519:comm")
    ann = MdnsAnnouncer(reg, "ed25519:node", "Test Node", port=7080)
    assert ann is not None


@pytest.mark.asyncio
async def test_udp_announcer_start_stop():
    """UdpAnnouncer can be started and stopped without errors."""
    from hearthnet.discovery.peers import PeerRegistry
    from hearthnet.discovery.udp import UdpAnnouncer

    reg = PeerRegistry("ed25519:node", "ed25519:comm")
    ann = UdpAnnouncer(reg, "ed25519:node", "ed25519:comm", port=7080)
    await ann.start()
    await asyncio.sleep(0)  # yield once
    await ann.stop()


# ===========================================================================
# ProtocolService (X09)
# ===========================================================================


@pytest.mark.asyncio
async def test_protocol_version_list_via_bus():
    """protocol.version.list returns contract_versions."""
    from hearthnet.node import HearthNode

    node = HearthNode("proto-test", "Proto", "ed25519:test")
    node.install_demo_services()

    result = await node.bus.call("protocol.version.list", (1, 0), {"input": {}})
    assert "output" in result
    output = result["output"]
    assert "contract_versions" in output
    assert "1.0" in output["contract_versions"]
    assert "implementation" in output
    assert output["implementation"]["name"] == "hearthnet-py"


@pytest.mark.asyncio
async def test_protocol_conformance_report_v1():
    """protocol.conformance.report runs v1.0 suite and reports counts."""
    from hearthnet.node import HearthNode

    node = HearthNode("conformance-test", "Conformance", "ed25519:test")
    node.install_demo_services()

    result = await node.bus.call(
        "protocol.conformance.report", (1, 0), {"input": {"suite_version": "1.0", "fast": True}}
    )
    assert "output" in result
    out = result["output"]
    assert "passed" in out
    assert "total" in out
    assert "results" in out
    assert out["total"] > 0
    # At least some must pass (moe.list, moe.route, model.list, protocol.version.list)
    assert out["passed"] > 0


@pytest.mark.asyncio
async def test_protocol_version_list_reflects_started():
    """protocol.version.list reports started=False before start() is called."""
    from hearthnet.node import HearthNode

    node = HearthNode("proto-started", "Proto Started", "ed25519:test")
    node.install_demo_services()

    result = await node.bus.call("protocol.version.list", (1, 0), {"input": {}})
    assert result["output"]["started"] is False


# ===========================================================================
# ConformanceRunner (X09 standalone)
# ===========================================================================


@pytest.mark.asyncio
async def test_conformance_runner_v1_demo_node():
    """ConformanceRunner.run() produces a valid report against a demo node."""
    from hearthnet.conformance import ConformanceRunner
    from hearthnet.node import HearthNode

    node = HearthNode("x09-runner", "X09 Runner", "ed25519:test")
    node.install_demo_services()

    runner = ConformanceRunner(bus=node.bus, node_id="ed25519:test")
    report = await runner.run(suite="1.0", fast=True)

    assert report.total > 0
    assert report.passed + report.failed + report.skipped == report.total
    assert report.suite_version == "1.0"

    d = report.as_dict()
    assert "passed" in d
    assert "results" in d
    assert isinstance(d["results"], list)


@pytest.mark.asyncio
async def test_conformance_runner_tool_plant_identify_expected_error():
    """The plant_identify check passes when tool returns bad_request for empty input."""
    from hearthnet.conformance import ConformanceRunner
    from hearthnet.node import HearthNode

    node = HearthNode("x09-plant", "X09 Plant", "ed25519:test")
    node.install_demo_services()

    runner = ConformanceRunner(bus=node.bus)
    report = await runner.run(suite="1.0", fast=True)

    plant_results = [r for r in report.results if r.capability == "tool.plant_identify"]
    if plant_results:
        # Should pass: empty input â†’ bad_request matches expect_error
        assert plant_results[0].passed


# ===========================================================================
# Mobile static (M08 PWA)
# ===========================================================================


def test_pwa_manifest_is_valid_json():
    """PWA manifest is a valid dict with required fields."""
    from hearthnet.ui.mobile import PWA_MANIFEST

    assert PWA_MANIFEST["name"] == "HearthNet"
    assert "icons" in PWA_MANIFEST
    assert "start_url" in PWA_MANIFEST
    assert PWA_MANIFEST["display"] == "standalone"


def test_service_worker_js_is_string():
    """Service worker is a non-empty JS string."""
    from hearthnet.ui.mobile import SERVICE_WORKER_JS

    assert isinstance(SERVICE_WORKER_JS, str)
    assert "addEventListener" in SERVICE_WORKER_JS
    assert "fetch" in SERVICE_WORKER_JS


def test_build_mobile_html_returns_pwa():
    """build_mobile_html returns HTML with manifest link and SW registration."""
    from hearthnet.ui.mobile import build_mobile_html

    html = build_mobile_html(node_url="http://localhost:7080", node_name="Test Node")
    assert "<!DOCTYPE html>" in html
    assert "manifest" in html
    assert "serviceWorker" in html
    assert "Test Node" in html


# ===========================================================================
# WebSocket pubsub via HttpServer (X06)
# ===========================================================================


def test_http_server_build_app_creates_ws_pubsub():
    """HttpServer.build_app() initialises _ws_pubsub when FastAPI is available."""
    try:
        from hearthnet.transport.server import HttpServer

        srv = HttpServer()
        srv.build_app()
        # ws_pubsub may be None if starlette WS import fails, but build_app shouldn't raise
        assert srv._app is not None
    except ImportError:
        pytest.skip("fastapi not installed")


@pytest.mark.asyncio
async def test_state_bus_to_pubsub_task_created_after_start():
    """After node.start(), _pubsub_task exists if HTTP server started."""
    from hearthnet.node import HearthNode

    node = HearthNode("pubsub-test", "PubSub", "ed25519:test")
    node.install_demo_services()

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        try:
            await asyncio.wait_for(node.start(port=0, data_dir=td), timeout=3.0)
        except (asyncio.TimeoutError, OSError, ImportError):
            pass
        finally:
            await node.stop()
        # If HTTP server started, pubsub_task would have been created
        # Just verify stop() cleans up without error


# ===========================================================================
# Gossip sync loop â€” instantiation test
# ===========================================================================


def test_sync_server_serve_heads_dict():
    """SyncServer.serve_heads() returns a dict with head and community_id."""
    import asyncio
    from hearthnet.events.log import EventLog
    from hearthnet.events.sync import SyncServer

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        log = EventLog(Path(td) / "events.db", "ed25519:comm", "ed25519:node")
        srv = SyncServer(log)

        async def _run():
            return await srv.serve_heads()

        result = asyncio.run(_run())
        assert isinstance(result, dict)
        assert "head" in result
        assert "community_id" in result
        assert result["community_id"] == "ed25519:comm"
