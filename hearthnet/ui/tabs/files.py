"""Files tab — BLAKE3 content-addressed blob store (M07)."""

from __future__ import annotations


def build_files_tab(bus=None):
    import gradio as gr

    with gr.Column():
        gr.Markdown("""### 🗂️ Files & Shared Blobs

All files are stored with a **BLAKE3 content hash** as their identifier (CID).
The same file uploaded on two different nodes gets the same CID — deduplication is automatic.

**How to use:**
- Upload any file — it is stored locally and advertised to the mesh
- Other nodes can fetch the file by CID via `bus.call("file.get", {"cid": ...})`
- On a multi-node mesh, files are available from any node that has them

**What works on HF Space:**  Local upload/list only (no peer nodes to share with)  
**What works locally:** Full mesh file sharing — any node can request any file from any peer
""")

        refresh_btn = gr.Button("🔄 Refresh List", size="sm")
        blobs_out = gr.JSON(label="Stored Files")

        gr.Markdown("#### Upload File")
        file_upload = gr.File(label="Choose file to upload to mesh", type="filepath")
        upload_btn = gr.Button("⬆ Upload", variant="primary")
        upload_result = gr.JSON(label="Upload Result", visible=False)

        gr.Markdown("#### Download File by CID")
        with gr.Row():
            cid_input = gr.Textbox(label="CID (paste from list above)", placeholder="blake3:...", scale=4)
            download_btn = gr.Button("⬇ Download", scale=1)
        download_file = gr.File(label="Download", visible=False)
        download_err = gr.Markdown(visible=False)

        async def do_refresh():
            if bus is None:
                return [{"info": "bus not connected — pass bus= to build_files_tab()"}]
            try:
                r = await bus.call("file.list", (1, 0), {"input": {}})
                files = r.get("output", {}).get("files", [])
                if not files:
                    return [{"info": "No files stored yet. Upload a file above."}]
                return files
            except Exception as e:
                return [{"error": str(e)}]

        async def do_upload(filepath):
            if not filepath:
                return (
                    gr.update(visible=True, value={"error": "No file selected"}),
                    gr.update(),  # blobs_out unchanged
                )
            if bus is None:
                return (
                    gr.update(visible=True, value={"error": "Bus not connected"}),
                    gr.update(),
                )
            try:
                import base64
                import os

                with open(filepath, "rb") as fh:
                    data = fh.read()
                data_b64 = base64.b64encode(data).decode()
                filename = os.path.basename(filepath)
                r = await bus.call(
                    "file.put",
                    (1, 0),
                    {"input": {"data_b64": data_b64, "filename": filename}},
                )
                # Auto-refresh the list
                list_r = await bus.call("file.list", (1, 0), {"input": {}})
                files = list_r.get("output", {}).get("files", [])
                return (
                    gr.update(visible=True, value=r.get("output", r)),
                    files or [{"info": "No files yet"}],
                )
            except Exception as e:
                return (
                    gr.update(visible=True, value={"error": str(e)}),
                    gr.update(),
                )

        async def do_download(cid: str):
            cid = (cid or "").strip()
            if not cid:
                return (
                    gr.update(visible=False),
                    gr.update(visible=True, value="⚠ Enter a CID first."),
                )
            if bus is None:
                return (
                    gr.update(visible=False),
                    gr.update(visible=True, value="⚠ Bus not connected."),
                )
            try:
                import base64
                import tempfile
                import os

                r = await bus.call("file.get", (1, 0), {"input": {"cid": cid}})
                if "error" in r:
                    return (
                        gr.update(visible=False),
                        gr.update(visible=True, value=f"⚠ {r['error']}"),
                    )
                out = r.get("output", {})
                data = base64.b64decode(out["data_b64"])
                filename = out.get("filename", cid[:16])
                # Write to a temp file so Gradio can serve it
                tmp = tempfile.NamedTemporaryFile(
                    delete=False, suffix="_" + filename, dir=tempfile.gettempdir()
                )
                tmp.write(data)
                tmp.close()
                return (
                    gr.update(visible=True, value=tmp.name),
                    gr.update(visible=False),
                )
            except Exception as e:
                return (
                    gr.update(visible=False),
                    gr.update(visible=True, value=f"⚠ Error: {e}"),
                )

        refresh_btn.click(do_refresh, outputs=blobs_out)
        upload_btn.click(do_upload, inputs=file_upload, outputs=[upload_result, blobs_out])
        download_btn.click(do_download, inputs=cid_input, outputs=[download_file, download_err])
