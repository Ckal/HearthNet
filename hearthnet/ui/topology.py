"""M08 — Topology visualisation component.

Spec: docs/M08-ui.md §3.2

Renders the live mesh topology and recent call traces as an HTML widget.
Updates are pushed via TopologyComponent.push_trace() and push_topology().
"""

from __future__ import annotations

import json
import time
from collections import deque
from typing import Any

try:
    import gradio as gr
    _HAS_GRADIO = True
except ImportError:
    _HAS_GRADIO = False


# Max recent call traces to keep in memory
_MAX_TRACES = 200
_MAX_TOPOLOGY_HISTORY = 10


class TopologyComponent:
    """Live mesh topology and call-trace viewer.

    Renders an HTML card showing:
    - Connected peers (node_id, capabilities count, latency)
    - Recent bus call traces (capability, duration_ms, success/error)
    - Local capability count

    Call push_trace() / push_topology() from bus hooks to keep it live.
    Integrate into Gradio UI via render().
    """

    def __init__(self, bus: Any = None) -> None:
        self._bus = bus
        self._traces: deque[dict] = deque(maxlen=_MAX_TRACES)
        self._topology: dict = {}
        self._last_updated: float = 0.0

    def push_trace(self, event: Any) -> None:
        """Accept a CallTraceEvent (or dict) and store it."""
        if hasattr(event, "__dict__"):
            rec = {
                "ts": getattr(event, "ts", time.strftime("%H:%M:%S")),
                "capability": getattr(event, "capability", "?"),
                "duration_ms": getattr(event, "duration_ms", 0),
                "success": getattr(event, "success", True),
                "error": getattr(event, "error", None),
                "peer_node_id": getattr(event, "peer_node_id", "local"),
            }
        elif isinstance(event, dict):
            rec = event
        else:
            return
        self._traces.appendleft(rec)
        self._last_updated = time.monotonic()

    def push_topology(self, snapshot: Any) -> None:
        """Accept a TopologySnapshot (or dict) and store it."""
        if isinstance(snapshot, dict):
            self._topology = snapshot
        elif hasattr(snapshot, "as_dict"):
            self._topology = snapshot.as_dict()
        elif hasattr(snapshot, "__dict__"):
            self._topology = vars(snapshot)
        self._last_updated = time.monotonic()

    def render(self) -> Any:
        """Return a Gradio HTML component showing current topology."""
        if not _HAS_GRADIO:
            raise ImportError("gradio is required for TopologyComponent.render()")

        html = self._build_html()
        return gr.HTML(value=html, label="Mesh Topology")

    def _build_html(self) -> str:
        peers = self._topology.get("peers", [])
        local_caps = self._topology.get("local_capabilities", 0)
        community = self._topology.get("community_id", "—")

        # Build peer rows
        peer_rows = ""
        for p in peers[:20]:
            nid = str(p.get("node_id", "?"))[:12]
            caps = p.get("capabilities_count", "?")
            lat = p.get("latency_ms", "?")
            peer_rows += f"<tr><td>{nid}…</td><td>{caps}</td><td>{lat}ms</td></tr>"
        if not peers:
            peer_rows = "<tr><td colspan='3' style='color:#888'>No peers discovered yet</td></tr>"

        # Build trace rows
        trace_rows = ""
        for t in list(self._traces)[:15]:
            cap = str(t.get("capability", "?"))[:35]
            dur = t.get("duration_ms", "?")
            ok = "✓" if t.get("success", True) else "✗"
            color = "#4ade80" if t.get("success", True) else "#f87171"
            trace_rows += f"<tr><td style='color:{color}'>{ok}</td><td>{cap}</td><td>{dur}ms</td></tr>"
        if not trace_rows:
            trace_rows = "<tr><td colspan='3' style='color:#888'>No calls yet</td></tr>"

        ts = time.strftime("%H:%M:%S") if self._last_updated else "never"

        return f"""
<div style="font-family:monospace;color:#e2e8f0;background:#16213e;padding:12px;border-radius:8px;border:1px solid #7c3aed">
  <div style="display:flex;justify-content:space-between;margin-bottom:8px">
    <span style="font-size:14px;font-weight:600;color:#a78bfa">Mesh Topology</span>
    <span style="font-size:11px;color:#64748b">updated {ts}</span>
  </div>
  <div style="margin-bottom:6px;font-size:12px;color:#94a3b8">
    Community: <b style="color:#c4b5fd">{community}</b> ·
    Local caps: <b style="color:#c4b5fd">{local_caps}</b> ·
    Peers: <b style="color:#c4b5fd">{len(peers)}</b>
  </div>
  <table style="width:100%;font-size:11px;border-collapse:collapse;margin-bottom:10px">
    <thead><tr style="color:#7c3aed"><th>Node</th><th>Caps</th><th>Latency</th></tr></thead>
    <tbody>{peer_rows}</tbody>
  </table>
  <div style="font-size:12px;color:#94a3b8;margin-bottom:4px">Recent calls</div>
  <table style="width:100%;font-size:11px;border-collapse:collapse">
    <thead><tr style="color:#7c3aed"><th></th><th>Capability</th><th>Duration</th></tr></thead>
    <tbody>{trace_rows}</tbody>
  </table>
</div>
"""

    def as_dict(self) -> dict:
        return {
            "topology": self._topology,
            "recent_traces": list(self._traces)[:20],
            "last_updated": self._last_updated,
        }
