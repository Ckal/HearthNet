// src/mesh/browsermesh.js
// Over-the-internet browser mesh using PeerJS (WebRTC). JavaScript only.
//
// Design (BitTorrent/rendezvous style, no custom server):
//   - DISCOVERY: a well-known "anchor" peer id is derived from the room name.
//     The first browser in a room claims that id and becomes the anchor. The
//     anchor only gossips a roster of member ids — it is a rendezvous point.
//   - DATA: every browser also runs its own random-id "self" peer. Members use
//     the roster to open direct WebRTC data channels to each other => full mesh.
//   - FAILOVER: if the anchor leaves, its id frees up and remaining members
//     periodically try to re-claim it, so the mesh self-heals.
//
// Requires global `Peer` from https://unpkg.com/peerjs (loaded in index.html).

function slug(s) {
  return String(s || "default").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "");
}

export function createMesh({ room = "hearthnet", name = "anon", onStatus, onPeers, onMessage } = {}) {
  const Peer = globalThis.Peer;
  if (!Peer) throw new Error("PeerJS not loaded (expected global `Peer`).");

  const anchorId = `hn-anchor-${slug(room)}`;
  const peers = new Map(); // selfId -> { conn, name }
  let self = null; // my mesh identity (random id)
  let selfId = null;
  let anchor = null; // Peer bound to anchorId if I'm the anchor
  let anchorConn = null; // my connection to the anchor (if I'm a member)
  let isAnchor = false;
  let reclaimTimer = null;
  let alive = false;

  const status = (extra = {}) =>
    onStatus?.({ room, anchorId, selfId, isAnchor, peers: [...peers.keys()], ...extra });

  const roster = () => [selfId, ...peers.keys()].filter(Boolean);

  // ── data mesh (self <-> self direct channels) ──────────────────────────────
  function wireDataConn(conn) {
    conn.on("open", () => {
      peers.set(conn.peer, { conn, name: conn.metadata?.name || conn.peer.slice(0, 6) });
      conn.send({ type: "presence", payload: { name } });
      onPeers?.(listPeers());
      status();
    });
    conn.on("data", (msg) => {
      if (!msg || typeof msg !== "object") return;
      if (msg.type === "presence" && peers.has(conn.peer)) {
        peers.get(conn.peer).name = msg.payload?.name || peers.get(conn.peer).name;
        onPeers?.(listPeers());
      }
      onMessage?.({ from: conn.peer, fromName: peers.get(conn.peer)?.name, type: msg.type, payload: msg.payload });
    });
    const drop = () => {
      if (peers.delete(conn.peer)) {
        onPeers?.(listPeers());
        status();
      }
    };
    conn.on("close", drop);
    conn.on("error", drop);
  }

  function connectTo(peerId) {
    if (!peerId || peerId === selfId || peers.has(peerId)) return;
    const conn = self.connect(peerId, { reliable: true, metadata: { name } });
    wireDataConn(conn);
  }

  function applyRoster(ids) {
    for (const id of ids) connectTo(id);
  }

  // ── anchor role: gossip the roster to all anchor clients ───────────────────
  function becomeAnchor() {
    isAnchor = true;
    const known = new Set([selfId]);
    const clients = new Set();

    const broadcast = () => {
      const members = [...known];
      for (const c of clients) {
        try {
          c.send({ type: "roster", payload: { members } });
        } catch { /* client gone */ }
      }
    };

    anchor.on("connection", (c) => {
      c.on("open", () => {
        clients.add(c);
        c.on("data", (m) => {
          if (m?.type === "hello" && m.payload?.selfId) {
            known.add(m.payload.selfId);
            broadcast();
          }
        });
        // tell the newcomer the current roster (incl. the anchor's own self id)
        c.send({ type: "roster", payload: { members: [...known] } });
        broadcast();
      });
      const gone = () => {
        clients.delete(c);
      };
      c.on("close", gone);
      c.on("error", gone);
    });

    status({ note: "became anchor" });
  }

  // ── member role: connect to the anchor, learn the roster ───────────────────
  function joinViaAnchor() {
    anchorConn = self.connect(anchorId, { reliable: true, metadata: { name } });
    anchorConn.on("open", () => {
      anchorConn.send({ type: "hello", payload: { selfId } });
      clearReclaim();
    });
    anchorConn.on("data", (m) => {
      if (m?.type === "roster") applyRoster(m.payload?.members || []);
    });
    const lost = () => {
      anchorConn = null;
      scheduleReclaim(); // anchor may have left — try to take over discovery
    };
    anchorConn.on("close", lost);
    anchorConn.on("error", lost);
  }

  function tryClaimAnchor() {
    if (!alive || isAnchor) return;
    const a = new Peer(anchorId);
    a.on("open", () => {
      anchor = a;
      becomeAnchor();
    });
    a.on("error", (err) => {
      a.destroy?.();
      if (err?.type === "unavailable-id") {
        // someone else is the anchor — connect to it
        if (!anchorConn) joinViaAnchor();
      }
    });
  }

  function scheduleReclaim() {
    clearReclaim();
    reclaimTimer = setInterval(tryClaimAnchor, 4000 + Math.random() * 3000);
  }
  function clearReclaim() {
    if (reclaimTimer) clearInterval(reclaimTimer);
    reclaimTimer = null;
  }

  function listPeers() {
    return [...peers.entries()].map(([id, v]) => ({ id, name: v.name }));
  }

  // ── public API ─────────────────────────────────────────────────────────────
  function join() {
    if (alive) return;
    alive = true;
    self = new Peer(); // random id
    self.on("open", (id) => {
      selfId = id;
      status({ note: "self online" });
      self.on("connection", (conn) => wireDataConn(conn)); // accept inbound mesh links
      tryClaimAnchor();
      scheduleReclaim();
    });
    self.on("error", (err) => status({ error: err?.type || String(err) }));
  }

  function leave() {
    alive = false;
    clearReclaim();
    for (const { conn } of peers.values()) conn.close?.();
    peers.clear();
    anchorConn?.close?.();
    anchor?.destroy?.();
    self?.destroy?.();
    self = anchor = anchorConn = null;
    selfId = null;
    isAnchor = false;
    onPeers?.([]);
    status({ note: "left" });
  }

  function broadcast(type, payload) {
    for (const { conn } of peers.values()) {
      try {
        conn.send({ type, payload });
      } catch { /* peer gone */ }
    }
  }

  function send(peerId, type, payload) {
    peers.get(peerId)?.conn?.send({ type, payload });
  }

  return {
    join,
    leave,
    broadcast,
    send,
    get id() { return selfId; },
    get peers() { return listPeers(); },
    get isAnchor() { return isAnchor; },
    get room() { return room; },
  };
}
