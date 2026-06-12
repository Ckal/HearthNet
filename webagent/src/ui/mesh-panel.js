// src/ui/mesh-panel.js
// PeerJS mesh UI: join a room, see peers, chat, and share news signals
// with other browsers over the internet.

import { createMesh } from "../mesh/browsermesh.js";

export function mountMeshPanel(root, { onShareSignals } = {}) {
  let mesh = null;
  const chatLog = [];

  root.innerHTML = `
    <div class="panel">
      <div class="panel-title">Browser mesh <span data-mesh-status class="pill">offline</span></div>
      <div class="row" style="margin-bottom:8px">
        <input data-room placeholder="room (community)" value="hearthnet" style="flex:0 0 160px" />
        <input data-name placeholder="your name" value="" />
        <button data-join class="primary">Join</button>
        <button data-leave disabled>Leave</button>
      </div>
      <div class="muted" style="font-size:12px;margin-bottom:8px" data-id>id: —</div>
      <div class="mesh-grid">
        <div>
          <div class="panel-title">Peers (<span data-peer-count>0</span>)</div>
          <div data-peers class="muted">No peers yet. Open this page in another tab/device and join the same room.</div>
        </div>
        <div>
          <div class="panel-title">Mesh chat</div>
          <div data-chat class="mesh-chat"></div>
          <div class="row" style="margin-top:8px">
            <input data-msg placeholder="message to mesh…" />
            <button data-send>Send</button>
          </div>
        </div>
      </div>
    </div>
  `;

  const $ = (s) => root.querySelector(s);
  const statusEl = $("[data-mesh-status]");
  const idEl = $("[data-id]");
  const peersEl = $("[data-peers]");
  const peerCount = $("[data-peer-count]");
  const chatEl = $("[data-chat]");

  function setStatus(text, cls = "") {
    statusEl.textContent = text;
    statusEl.className = `pill ${cls}`;
  }

  function renderPeers(peers) {
    peerCount.textContent = peers.length;
    peersEl.innerHTML = peers.length
      ? peers.map((p) => `<div class="peer-row"><span class="pill ok">${esc(p.name)}</span> <span class="muted mono">${p.id.slice(0, 10)}</span></div>`).join("")
      : "<span class='muted'>No peers yet.</span>";
  }

  function pushChat(who, text, cls = "") {
    chatLog.push({ who, text, cls });
    chatEl.innerHTML = chatLog.slice(-100).map((m) => `<div class="msg ${m.cls}"><b>${esc(m.who)}:</b> ${esc(m.text)}</div>`).join("");
    chatEl.scrollTop = chatEl.scrollHeight;
  }

  function join() {
    const room = $("[data-room]").value.trim() || "hearthnet";
    const name = $("[data-name]").value.trim() || `peer-${Math.random().toString(36).slice(2, 6)}`;
    setStatus("connecting…", "warn");

    mesh = createMesh({
      room,
      name,
      onStatus: (st) => {
        if (st.error) setStatus(`error: ${st.error}`, "err");
        else setStatus(st.isAnchor ? "online · anchor" : "online", "ok");
        idEl.textContent = `id: ${st.selfId || "—"}  ·  anchor: ${st.anchorId}`;
      },
      onPeers: renderPeers,
      onMessage: ({ fromName, type, payload }) => {
        if (type === "chat") pushChat(fromName || "peer", payload?.text || "");
        else if (type === "signals") {
          const names = (payload?.signals || []).map((s) => s.name).join(", ");
          pushChat(fromName || "peer", `shared active signals: ${names}`, "sys");
          onShareSignals?.(payload?.signals || [], fromName);
        }
      },
    });
    mesh.join();
    $("[data-join]").disabled = true;
    $("[data-leave]").disabled = false;
    pushChat("system", `joined room "${room}" as ${name}`, "sys");
  }

  function leave() {
    mesh?.leave();
    mesh = null;
    renderPeers([]);
    setStatus("offline");
    $("[data-join]").disabled = false;
    $("[data-leave]").disabled = true;
    pushChat("system", "left mesh", "sys");
  }

  function sendMsg() {
    const inp = $("[data-msg]");
    const text = inp.value.trim();
    if (!text || !mesh) return;
    mesh.broadcast("chat", { text });
    pushChat("you", text, "self");
    inp.value = "";
  }

  $("[data-join]").onclick = join;
  $("[data-leave]").onclick = leave;
  $("[data-send]").onclick = sendMsg;
  $("[data-msg]").addEventListener("keydown", (e) => { if (e.key === "Enter") sendMsg(); });

  return {
    shareSignals: (signals) => mesh?.broadcast("signals", { signals }),
    get mesh() { return mesh; },
  };
}

function esc(s) {
  return String(s || "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}
