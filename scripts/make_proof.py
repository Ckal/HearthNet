"""Generate an HTML proof page from a real routed call to the live HF Space."""

from __future__ import annotations

import datetime
import html

import httpx

BASE = "https://build-small-hackathon-hearthnet.hf.space"


def call(cap: str, inp: dict) -> dict:
    r = httpx.post(
        f"{BASE}/bus/v1/call",
        json={"capability": cap, "version": "1.0", "input": inp},
        timeout=90,
        follow_redirects=True,
    )
    return r.json()


def main() -> None:
    man = httpx.get(f"{BASE}/manifest", timeout=60, follow_redirects=True).json()
    chat = call("llm.chat", {"messages": [{"role": "user", "content": "In one sentence, how do I store water safely?"}]})
    rag = call("rag.list_corpora", {})

    node = man.get("node_id", "?")
    caps = [c.get("name") if isinstance(c, dict) else c for c in man.get("capabilities", [])]
    ans = chat["output"]["message"]["content"]
    model = chat["meta"]["model"]
    ms = chat["meta"]["ms"]
    corp = rag["output"]["corpora"]
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    doc = f"""<html><head><meta charset="utf-8"><style>
*{{box-sizing:border-box}}
body{{background:#0d1117;color:#c9d1d9;font-family:Consolas,monospace;padding:18px;width:500px;
overflow-wrap:break-word;word-break:break-word}}
h1{{color:#ff7a18;font-size:18px}} .ok{{color:#3fb950}} .k{{color:#58a6ff}}
.box{{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:14px;margin:10px 0;font-size:13px}}
.ans{{color:#e3b341}} small{{color:#8b949e}}</style></head><body>
<h1>HearthNet - Local node connected to live HF Space</h1>
<small>{ts} &middot; HTTPS over the capability bus</small>
<div class="box"><span class="ok">[1]</span> Peered with <span class="k">build-small-hackathon-hearthnet.hf.space</span><br>
Remote node_id: <span class="k">{html.escape(node)}</span><br>
Remote capabilities routable: <b>{len(caps)}</b></div>
<div class="box"><span class="ok">[2]</span> Routed <span class="k">llm.chat</span> to Space model
<span class="k">{html.escape(model)}</span> ({ms} ms)<br><br>
Q: In one sentence, how do I store water safely?<br>
A: <span class="ans">{html.escape(ans)}</span></div>
<div class="box"><span class="ok">[3]</span> Routed <span class="k">rag.list_corpora</span> to shared corpora:
<span class="ans">{html.escape(", ".join(corp))}</span></div>
<div class="box"><small>Caps: {html.escape(", ".join(caps))}</small></div>
</body></html>"""

    with open("docs/screenshots/_proof.html", "w", encoding="utf-8") as fh:
        fh.write(doc)
    print(f"wrote proof html; caps={len(caps)} model={model}")


if __name__ == "__main__":
    main()
