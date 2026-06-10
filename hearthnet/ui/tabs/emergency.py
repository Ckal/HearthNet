"""Emergency tab — shows when offline."""
from __future__ import annotations


def build_emergency_tab(bus=None, state_bus=None):
    import gradio as gr

    with gr.Column():
        gr.Markdown("### 🚨 Emergency Mode")

        status_out = gr.JSON(label="Current Mode")
        refresh_btn = gr.Button("Check Status", variant="secondary")

        gr.Markdown("#### Local Resources")
        gr.Markdown("In offline mode, all capabilities route to local nodes only.")

        if bus is not None:
            with gr.Row():
                probe_btn = gr.Button("Run Connectivity Probe", variant="secondary")
                probe_out = gr.JSON(visible=False)

        def get_status():
            if state_bus is None:
                return {"mode": "unknown", "message": "State bus not connected"}
            s = state_bus.current()
            return {
                "mode": s.mode,
                "probe_results": s.probe_results,
                "label": s.mode_label,
            }

        refresh_btn.click(get_status, outputs=status_out)
