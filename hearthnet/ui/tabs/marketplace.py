"""Marketplace tab."""

from __future__ import annotations


def build_marketplace_tab(bus=None):
    import gradio as gr

    with gr.Column():
        gr.HTML("""
<div style="background:linear-gradient(135deg,#1e1b4b,#312e81);
            border-radius:10px;padding:16px 20px;margin-bottom:8px;
            border:1px solid #4f46e5">
  <h3 style="color:#fff;margin:0">🛒 Community Marketplace</h3>
  <p style="color:rgba(255,255,255,.7);margin:4px 0 0;font-size:.85em">
    Post services · share resources · trade capabilities across the mesh
  </p>
</div>
""")
        gr.Markdown("### Community Marketplace")

        refresh_btn = gr.Button("🔄 Refresh", size="sm")
        posts_out = gr.JSON(label="Active Posts")

        gr.Markdown("#### Post Something")
        with gr.Row():
            post_title = gr.Textbox(label="Title", scale=3)
            post_cat = gr.Dropdown(
                label="Category",
                choices=["offer", "request", "info", "emergency"],
                value="info",
                scale=1,
            )
        post_body = gr.Textbox(label="Description", lines=3)
        post_btn = gr.Button("Post", variant="primary")
        post_result = gr.JSON(label="Result", visible=False)

        async def do_refresh():
            if bus is None:
                return [{"info": "Bus not connected — run as a real node to see live posts"}]
            try:
                r = await bus.call("market.list", (1, 0), {"input": {}})
                return r.get("output", {}).get("posts", [])
            except Exception as e:
                return [{"error": str(e)}]

        async def do_post(title, category, body):
            if bus is None:
                return gr.update(visible=True, value={"error": "Bus not connected"})
            if not title or not body:
                return gr.update(visible=True, value={"error": "Title and body required"})
            try:
                r = await bus.call(
                    "market.post",
                    (1, 0),
                    {"input": {"title": title, "category": category, "body": body}},
                )
                return gr.update(visible=True, value=r.get("output", {}))
            except Exception as e:
                return gr.update(visible=True, value={"error": str(e)})

        refresh_btn.click(do_refresh, outputs=posts_out)
        post_btn.click(do_post, inputs=[post_title, post_cat, post_body], outputs=post_result)
