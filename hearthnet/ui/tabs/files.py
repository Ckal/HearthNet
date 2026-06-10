"""Files tab."""
from __future__ import annotations


def build_files_tab(bus=None):
    import gradio as gr

    with gr.Column():
        gr.Markdown("### Files & Blobs")

        refresh_btn = gr.Button("🔄 Refresh", size="sm")
        blobs_out = gr.JSON(label="Available Blobs")

        gr.Markdown("#### Upload File")
        file_upload = gr.File(label="Upload file to mesh")
        upload_btn = gr.Button("Upload", variant="primary")
        upload_result = gr.JSON(visible=False)

        async def do_refresh():
            if bus is None:
                return []
            try:
                r = await bus.call("file.list", (1, 0), {"input": {}})
                return r.get("output", {}).get("blobs", [])
            except Exception as e:
                return [{"error": str(e)}]

        async def do_upload(file_obj):
            if file_obj is None:
                return gr.update(visible=True, value={"error": "No file selected"})
            if bus is None:
                return gr.update(visible=True, value={"error": "Bus not connected"})
            try:
                import base64

                if hasattr(file_obj, "read"):
                    data = file_obj.read()
                else:
                    with open(file_obj.name, "rb") as fh:
                        data = fh.read()
                data_b64 = base64.b64encode(data).decode()
                filename = (
                    getattr(file_obj, "name", "unknown")
                    .split("/")[-1]
                    .split("\\")[-1]
                )
                r = await bus.call(
                    "file.put",
                    (1, 0),
                    {"input": {"data_b64": data_b64, "filename": filename}},
                )
                return gr.update(visible=True, value=r.get("output", {}))
            except Exception as e:
                return gr.update(visible=True, value={"error": str(e)})

        refresh_btn.click(do_refresh, outputs=blobs_out)
        upload_btn.click(do_upload, inputs=file_upload, outputs=upload_result)
