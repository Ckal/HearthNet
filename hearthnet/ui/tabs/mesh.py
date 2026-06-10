"""Mesh Network tab — live topology from the capability bus registry.

Shows all peers this node has discovered, their capabilities, and an SVG
topology graph. Data is sourced exclusively from bus.registry.all_remote()
and bus.registry.all_local() — no hardcoded or simulated nodes.

Spec: docs/M02-discovery.md, docs/M03-bus.md §4 (registry)
"""

from __future__ import annotations

import html as html_lib
import math


def _topology_svg(this_node: str, peers: list[dict]) -> str:
    """Build an SVG graph from live registry data. No fake data."""
    all_nodes = [{"id": this_node[:24], "role": "this node", "is_self": True}]
    for p in peers:
        all_nodes.append(
            {
                "id": p["node_id"][:24],
                "role": f"{p['capability_count']} caps",
                "is_self": False,
            }
        )

    if len(all_nodes) == 1:
        return (
            "<div style='text-align:center;padding:48px;color:#888;background:#0d1f1c;"
            "border-radius:8px'>"
            "<p style='font-size:1.2em'>No peers discovered yet.</p>"
            "<p>Start a second HearthNet node and run <code>net.mesh_discover()</code>,"
            " or enable mDNS/UDP discovery.</p>"
            "<p>See <b>docs/HOWTO.md §3</b> for step-by-step instructions.</p>"
            "</div>"
        )

    n = len(all_nodes)
    cx, cy, r_orbit = 250, 220, 150
    items: list[tuple[float, float, dict]] = []
    for i, node in enumerate(all_nodes):
        angle = (i / n) * math.tau - math.pi / 2
        x = cx + r_orbit * math.cos(angle)
        y = cy + r_orbit * math.sin(angle)
        items.append((x, y, node))

    lines: list[str] = []
    circles: list[str] = []
    labels: list[str] = []

    # Lines from this node to each peer
    self_x, self_y = items[0][0], items[0][1]
    for x, y, node in items[1:]:
        lines.append(
            f'<line x1="{self_x:.1f}" y1="{self_y:.1f}" x2="{x:.1f}" y2="{y:.1f}" '
            f'stroke="#4CAF50" stroke-width="1.5" opacity="0.5" stroke-dasharray="5,3"/>'
        )

    for x, y, node in items:
        fill = "#4CAF50" if node["is_self"] else "#2196F3"
        circles.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="18" fill="{fill}" opacity="0.85"/>')
        labels.append(
            f'<text x="{x:.1f}" y="{y - 24:.1f}" text-anchor="middle" '
            f'fill="white" font-size="10" font-family="monospace">'
            f"{html_lib.escape(node['id'])}</text>"
        )
        labels.append(
            f'<text x="{x:.1f}" y="{y + 30:.1f}" text-anchor="middle" '
            f'fill="#aaa" font-size="8">{html_lib.escape(node["role"])}</text>'
        )

    svg = (
        '<svg viewBox="0 0 500 440" style="width:100%;max-width:560px;'
        'background:#0d1f1c;border-radius:8px;display:block;margin:auto">'
        + "".join(lines)
        + "".join(circles)
        + "".join(labels)
        + "</svg>"
        '<p style="color:#888;font-size:11px;text-align:center;margin-top:6px">'
        "🟢 this node &nbsp;|&nbsp; 🔵 peers &nbsp;|&nbsp; "
        "dashed lines = active capability-bus connections</p>"
    )
    return svg


def build_mesh_tab(bus=None):
    import gradio as gr

    with gr.Column():
        gr.Markdown("""### 🌐 Mesh Network

Live view of every node this HearthNet instance has discovered.
Each entry is a real peer registered in the capability bus — no simulated data.

**How peers appear here:**
1. Run a second HearthNet node on the same LAN
2. Both nodes auto-discover each other via mDNS/UDP (M02)
3. Each node advertises its capabilities on the bus (M03)
4. Click **Refresh** to pull the current registry snapshot
""")

        with gr.Row():
            refresh_btn = gr.Button("🔄 Refresh Mesh", variant="primary", scale=2)

        mesh_html = gr.HTML(
            value="<p style='color:#888;padding:16px'>Click Refresh to load live mesh topology.</p>"
        )

        with gr.Row():
            stats_out = gr.JSON(label="Mesh Statistics", visible=False, scale=2)
            caps_out = gr.JSON(label="Capability Matrix", visible=False, scale=3)

        async def get_mesh():
            if bus is None:
                svg = (
                    "<div style='padding:24px;background:#1a1a1a;border-radius:8px;color:#f44'>"
                    "<b>Bus not connected.</b> Run as a real HearthNet node to see live mesh topology."
                    "</div>"
                )
                return svg, gr.update(visible=False), gr.update(visible=False)
            try:
                remote_entries = list(bus.registry.all_remote())
                local_entries = list(bus.registry.all_local())

                peer_caps: dict[str, list[str]] = {}
                for e in remote_entries:
                    nid = e.node_id
                    peer_caps.setdefault(nid, []).append(
                        f"{e.descriptor.name}@{e.descriptor.version[0]}.{e.descriptor.version[1]}"
                    )

                peers = [
                    {
                        "node_id": nid,
                        "capabilities": caps,
                        "capability_count": len(caps),
                    }
                    for nid, caps in peer_caps.items()
                ]

                this_node = getattr(bus, "node_id_full", "this-node")
                local_caps = [
                    f"{e.descriptor.name}@{e.descriptor.version[0]}.{e.descriptor.version[1]}"
                    for e in local_entries
                ]

                svg = _topology_svg(this_node, peers)

                stats = {
                    "this_node": this_node,
                    "peer_count": len(peers),
                    "local_capabilities": len(local_caps),
                    "total_mesh_capabilities": len(local_caps)
                    + sum(p["capability_count"] for p in peers),
                }

                # Capability matrix: which node has what
                all_cap_names: set[str] = set(local_caps)
                for p in peers:
                    all_cap_names.update(p["capabilities"])
                matrix = {
                    "this_node": {c: (c in local_caps) for c in sorted(all_cap_names)},
                }
                for p in peers:
                    matrix[p["node_id"][:20]] = {
                        c: (c in p["capabilities"]) for c in sorted(all_cap_names)
                    }

                return (
                    svg,
                    gr.update(visible=True, value=stats),
                    gr.update(visible=True, value=matrix),
                )
            except Exception as exc:
                err = f"<p style='color:#f44'>Error loading mesh: {html_lib.escape(str(exc))}</p>"
                return err, gr.update(visible=False), gr.update(visible=False)

        refresh_btn.click(get_mesh, outputs=[mesh_html, stats_out, caps_out])
