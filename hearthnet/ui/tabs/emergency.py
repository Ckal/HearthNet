"""Emergency tab — offline-mode probe and connectivity status (M09)."""

from __future__ import annotations


def build_emergency_tab(bus=None, state_bus=None):
    import gradio as gr

    with gr.Column():
        gr.Markdown("""### 🚨 Emergency Mode

HearthNet monitors internet connectivity and automatically switches modes:

| Mode | Meaning | LLM routing |
|------|---------|-------------|
| `normal` | Internet reachable | Local preferred, online fallback allowed |
| `degraded` | Partial connectivity | Local only, known-good peers only |
| `offline` | No internet | Strict local-only, internet capabilities deregistered |

Click **Check Status** to see the current mode. On a real node, the detector
runs a background probe every 30 seconds against multiple endpoints.
""")

        status_out = gr.JSON(label="Current Mode")
        refresh_btn = gr.Button("Check Status", variant="secondary")

        gr.Markdown("#### Local Resources")
        gr.Markdown("In offline mode, all capabilities route to local nodes only.")

        if bus is not None:
            with gr.Row():
                probe_btn = gr.Button("Run Connectivity Probe", variant="secondary")
                probe_out = gr.JSON(label="Probe Results", visible=False)

        def get_status():
            if state_bus is None:
                return {"mode": "unknown", "message": "State bus not connected"}
            s = state_bus.current()
            return {
                "mode": s.mode,
                "probe_results": s.probe_results,
                "label": s.mode_label,
            }

        def run_probe():
            """Run a synchronous connectivity probe and update state_bus."""
            import socket
            import urllib.request

            targets = {
                "dns:1.1.1.1": False,
                "dns:8.8.8.8": False,
                "http:cloudflare.com": False,
            }
            # DNS probes
            for host in ("1.1.1.1", "8.8.8.8"):
                try:
                    socket.getaddrinfo(host, 53, timeout=3)
                    targets[f"dns:{host}"] = True
                except Exception:
                    pass
            # HTTP probe
            try:
                urllib.request.urlopen("https://cloudflare.com", timeout=5)  # nosec B310
                targets["http:cloudflare.com"] = True
            except Exception:
                pass

            if state_bus is not None:
                state_bus.emit_probe(targets)
            return get_status(), gr.update(visible=True, value=targets)

        refresh_btn.click(get_status, outputs=status_out)

        if bus is not None:
            probe_btn.click(run_probe, outputs=[status_out, probe_out])
