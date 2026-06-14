# HearthNet — Hackathon Final Step Plan

*Prepared June 14, 2026 · deadline June 15*

This document is the ground truth for what is fixed, what is still open, and what
to do next — in exact priority order. Every item has a file reference.

---

## Part 1 — Bugs Fixed in This Session

All of these were silent failures that made the live demo diverge from the
architecture described in the README.

### FIX-1 · `node.start()` never set `_started = True`

**File:** [hearthnet/node.py](hearthnet/node.py#L628)  
**Symptom:** `node.stop()` was guarded by `if not self._started: return` and therefore
always exited immediately without cancelling background tasks, shutting down the HTTP
server, or stopping mDNS. Double-starting was also possible.  
**Fix:** Added `self._started = True` at the end of `start()`, just before the
"HearthNode ready" log line.

### FIX-2 · Silent exception swallowing in `ChatService.send()`

**File:** [hearthnet/services/chat/service.py](hearthnet/services/chat/service.py#L112)  
**Symptom:** When `event_log` path failed (disk full, SQLite lock, etc.) the exception
was swallowed with a bare `except Exception: pass`. Messages appeared sent but were
never persisted. Failure was completely invisible to operators.  
**Fix:** Replaced with `_log.warning(...)` so failures appear in logs while graceful
fallback to in-memory mode is preserved.

### FIX-3 · `UTC = UTC` dead re-assignments

**Files:**
- [hearthnet/services/chat/service.py](hearthnet/services/chat/service.py#L9)
- [hearthnet/services/marketplace/service.py](hearthnet/services/marketplace/service.py#L9)

**Symptom:** Copy-paste artifact — `UTC` was defined on one line and immediately
re-assigned to itself on the next. Harmless but signals unreviewed code.  
**Fix:** Removed the duplicate assignments and cleaned up import ordering.

### FIX-4 · `RagService` wrote corpora to current working directory

**File:** [hearthnet/services/rag/service.py](hearthnet/services/rag/service.py#L21)  
**Symptom:** `corpora_dir` defaulted to `Path(".")`. On HF Space the cwd is the
(potentially read-only) repo root. Ingest appeared to work but all corpus data was
written to an unreliable location and lost on restart.  
**Fix:** Default changed to `Path.home() / ".hearthnet" / "corpora"`. Always writable
on local machines; overridden explicitly in `app.py` using `HEARTHNET_DATA_DIR`.

### FIX-5 · Seed corpus was never actually ingested

**Files:** [app.py](app.py#L360), [hearthnet/services/rag/service.py](hearthnet/services/rag/service.py#L103)  
**Symptom (two parts):**
1. `_seed_corpus()` sent `{"documents": [...]}` but `handle_ingest()` only read
   `inp.get("text", "")`, so every seed call indexed an empty string. The 10-document
   emergency corpus (water safety, CPR, first aid…) was silently empty.
2. `asyncio.run(_seed_corpus())` failed silently when a loop was already running
   (Gradio may have started one first), suppressed by `contextlib.suppress(Exception)`.

**Fix (part 1):** Added batch-document dispatch to `handle_ingest`: detects
`{"documents": [...]}`, re-dispatches each as a single-document call, returns
`{"batch": [...], "count": N}`.  
**Fix (part 2):** Replaced `asyncio.run()` with a dedicated daemon thread that creates
its own event loop — no conflict with any running loop, 60 s timeout so it doesn't
block Space startup.

### FIX-6 · Sticky session memory leak in Router

**File:** [hearthnet/bus/router.py](hearthnet/bus/router.py#L54)  
**Symptom:** `_sticky: dict[str, CapabilityEntry]` grew without bound. On a long-lived
community node serving thousands of sessions, this is a real memory leak.  
**Fix:** Added `_MAX_STICKY_SESSIONS = 10_000` cap. Dict is insertion-ordered;
when the cap is hit, the oldest entries are evicted (LRU-by-insertion) before
adding a new one.

### FIX-7 · `app.py` seed corpus wrote to wrong directory

**File:** [app.py](app.py#L350)  
**Symptom:** `RagService` was created without `corpora_dir`, so it used the cwd
default (fixed in FIX-4). On HF Space this is the repo root, which may not be
writable and is not in `HEARTHNET_DATA_DIR`.  
**Fix:** `app.py` now derives `_corpora_dir` from `HEARTHNET_DATA_DIR` (same pattern
as the event log and blob store) and passes it explicitly to `RagService`.

---

## Part 2 — Outstanding Issues (prioritised)

These are open gaps that still make the demo diverge from the architecture.
In order of hackathon impact.

---

### OPEN-1 · Relay hub roster lost on Space restart (HIGH)

**File:** [hearthnet/transport/relay_hub.py](hearthnet/transport/relay_hub.py#L58)  
**Problem:** `RelayHub._members` is an in-memory Python dict. HF Spaces restart their
containers regularly (zero-GPU timeout, quota rotation). Every restart evicts all
peers. A node that joined yesterday silently disappears.  
**Impact:** The entire internet-mesh story breaks after the first Space restart.
Any user who joined via QR invite has to re-join manually.

**Fix approach:**
```python
# relay_hub.py — add SQLite-backed persistence
import sqlite3, json

class RelayHub:
    def __init__(self, *, db_path: Path | None = None, ...):
        self._db = sqlite3.connect(str(db_path or ":memory:"), check_same_thread=False)
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS members (
                node_id TEXT PRIMARY KEY,
                data TEXT NOT NULL,   -- JSON _Member fields
                last_seen REAL NOT NULL
            )
        """)
        self._db.commit()
        self._restore_members()  # reload on startup
```
Add `_persist_member()` call inside `join()` and `_prune_stale()` to delete from SQLite.
Estimated effort: **3 hours**.

---

### OPEN-2 · `node.start()` not called in `app.py` — mDNS/HTTP transport silent (HIGH)

**File:** [app.py](app.py#L395)  
**Problem:** `app.py` manually wires services but never calls `await node.start()`.
This means:
- mDNS and UDP peer discovery never start → nodes can't find each other on LAN
- The FastAPI HTTP transport never starts → remote peers can't call this node's bus
  via port 7080
- The gossip sync loop never starts → event log is local-only

**Why it was deferred:** HF Space runs in a ZeroGPU container without mDNS
capability, so the Space itself benefits less. But local nodes launched via
`python app.py` also miss these features.

**Fix approach:**
The Space should still avoid `node.start()` (no mDNS, public port not exposed).
Local nodes should call `node.start()` and get the full stack.
Solution: gate on whether we're on HF Space:

```python
# in app.py _build_node(), at the end:
if not os.getenv("SPACE_HOST"):
    # Local dev — start full networking stack
    import asyncio, threading
    def _start_node():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(node.start(port=7080))
        loop.run_forever()
    threading.Thread(target=_start_node, daemon=True, name="hearthnet-node").start()
```

Estimated effort: **2 hours**. Needs testing that the HTTP server doesn't conflict
with Gradio's port.

---

### OPEN-3 · Event log not injected into Marketplace/Chat at runtime (MEDIUM)

**Files:** [hearthnet/node.py](hearthnet/node.py#L344), [app.py](app.py#L391)  
**Problem:** `node.start()` injects `event_log` into `RagService` (line 606).
But `ChatService` and `MarketplaceService` get their `event_log` only if passed at
construction — which `install_services()` doesn't do (no event_log known yet).
On HF Space `app.py` passes it correctly, but local nodes using `install_services()`
get in-memory chat/marketplace.

**Fix:** In `node.install_services()`, store references to the service instances so
`node.start()` can inject event_log into them alongside RagService:

```python
# node.py install_services() — keep references
self._chat_service = ChatService(self.node_id, bus=self.bus)
self._market_service = MarketplaceService()
...

# node.start() — inject after EventLog is open
if self._chat_service is not None:
    self._chat_service._event_log = self._event_log
if self._market_service is not None:
    self._market_service._event_log = self._event_log
```

Estimated effort: **1 hour**.

---

### OPEN-4 · Token `exp` claim not enforced in Router (MEDIUM)

**File:** [hearthnet/bus/router.py](hearthnet/bus/router.py)  
**Problem:** M16 capability tokens have an `exp` field in their JWT-style payload.
`AuthService` validates signatures but the router's `route()` method never checks
expiry. An expired token grants permanent access.

**Fix:** Add expiry check in `CapabilityEntry.is_authorized(token)` or in the bus
`handle_call()` before routing:

```python
# bus/__init__.py handle_call()
if req.token:
    exp = parse_token_exp(req.token)
    if exp and time.time() > exp:
        return {"error": "token_expired", "message": "Capability token has expired"}
```

Estimated effort: **2 hours**.

---

### OPEN-5 · Live mesh topology not auto-refreshing in Mesh tab (LOW)

**File:** [hearthnet/ui/tabs/mesh.py](hearthnet/ui/tabs/mesh.py)  
**Problem:** `WebSocketPubSub` (X06) publishes `peer.discovered` and
`emergency.mode.changed` events. The Mesh tab renders a static SVG that only
updates when the user manually clicks "Refresh". Judges see a static graph even
when peers join live.

**Fix:** Use Gradio's `gr.Timer` (≥4.x) or polling interval to auto-refresh the SVG
every 5 seconds:

```python
# mesh.py
timer = gr.Timer(value=5)
timer.tick(fn=refresh_topology, outputs=topology_svg)
```

Estimated effort: **30 minutes**.

---

### OPEN-6 · Peer capability matrix missing from Mesh tab (LOW)

**File:** [hearthnet/ui/tabs/mesh.py](hearthnet/ui/tabs/mesh.py)  
**Problem:** The Mesh tab shows peer nodes as SVG circles but gives no indication of
what each peer can do. A judge can't see that Node B has `ocr.extract` but not
`llm.chat`.

**Fix:** Add a `gr.DataFrame` below the topology SVG:

```python
def _capability_matrix(bus) -> list[list]:
    rows = []
    for peer in bus.registry.all_remote():
        rows.append([peer.node_id[:16], peer.descriptor.name, "✓"])
    return rows

cap_df = gr.DataFrame(headers=["Node", "Capability", "Status"])
refresh_btn.click(fn=lambda: _capability_matrix(bus), outputs=cap_df)
```

Estimated effort: **1 hour**.

---

### OPEN-7 · Routing trace is raw text, not visual (LOW)

**File:** [hearthnet/ui/tabs/ask.py](hearthnet/ui/tabs/ask.py)  
**Problem:** The `_routed_via` field is shown as plain text. The README shows a flow
diagram. Judges get `"local-abc123"` instead of `"🏠 Local · score 0.94 · 23 ms"`.

**Fix:** Parse `_routed_via` and render a formatted badge:

```python
def _format_route(routed_via: str, ms: int) -> str:
    if routed_via.startswith("local"):
        return f"🏠 **Local** · {ms} ms"
    return f"🌐 **Remote** `{routed_via[:16]}` · {ms} ms"
```

Estimated effort: **30 minutes**.

---

## Part 3 — Prize Actions (deadline June 15)

| # | Action | Effort | Prize target |
|---|--------|--------|--------------|
| P1 | Record 2–4 min demo video (OBS/Loom) | 2 h | All prizes — mandatory |
| P2 | Post on X @zX14_7 with Space link + video | 15 min | Best Demo badge |
| P3 | Set `NVIDIA_API_KEY` in HF Space secrets | 5 min | Nemotron RTX 5080 |
| P4 | Deploy `app_nemotron.py` as second HF Space | 30 min | NVIDIA + Off Brand |
| P5 | Set `MINICPM_URL` or swap default model to MiniCPM3-4B | 1 h | OpenBMB $2,500 |
| P6 | `modal deploy scripts/modal_deploy.py` + set secret | 1 h | Modal $10k credits |
| P7 | GitHub Codex commits in mirrored repo | 2 h | OpenAI $5,000 |

**P1 demo video script** (exact flow judges want to see):
1. Open HF Space → all 8 tabs visible
2. Ask tab: type "What do I do if water is cut off?" → show RAG answer + routing trace
3. Toggle Agent Mode → ask multi-step question → show Thought/Tool/Observation steps
4. Mesh tab: show live topology SVG (even single node is fine)
5. Chat tab: send a message to self / another node
6. Emergency tab: click "Check Connectivity" → show probe results
7. Settings tab: generate invite QR code
8. 10-second clip of `app_nemotron.py` doing structured extraction

---

## Part 4 — Test Additions Needed

| Test | What it covers | File to create |
|------|----------------|----------------|
| `test_node_started_flag` | `node.start()` sets `_started=True`; `node.stop()` resets it and cancels tasks | `tests/test_node_lifecycle.py` |
| `test_rag_documents_batch` | `handle_ingest` with `{"documents": [...]}` indexes all docs | `tests/test_rag_ingest_batch.py` |
| `test_sticky_session_eviction` | Router evicts oldest sessions at `_MAX_STICKY_SESSIONS` cap | `tests/test_bus_router_memory.py` |
| `test_chat_service_log_on_error` | Exception in event_log path is logged, not swallowed | `tests/test_chat_service.py` |
| `test_corpora_dir_default` | `RagService()` uses `~/.hearthnet/corpora`, not `cwd` | `tests/test_rag_service_defaults.py` |
| `test_relay_hub_sqlite` | Relay hub persists member on join; restores on init | `tests/test_relay_persistence.py` |

---

## Part 5 — Deployment Checklist (HF Space)

```
[ ] NVIDIA_API_KEY secret set → Nemotron backend auto-activates
[ ] MODAL_ENDPOINT secret set → Modal backend auto-activates
[ ] MINICPM_URL secret set    → MiniCPM backend auto-activates
[ ] HEARTHNET_DATA_DIR set    → persistent data survives Space restarts
    recommended: /data/hearthnet  (HF Spaces /data is persistent)
[ ] Confirm Space runs on ZeroGPU (not CPU-only)
[ ] Demo video URL in README
[ ] Social post URL in README
```

---

## Part 6 — Local Node Checklist (after deadline)

```
[ ] pip install hearthnet  → publish to PyPI (pyproject.toml already correct)
[ ] node.start() for local mode (OPEN-2)
[ ] ChatService / MarketplaceService event_log injection (OPEN-3)
[ ] Relay hub SQLite persistence (OPEN-1)
[ ] Token expiry enforcement (OPEN-4)
[ ] Auto-refresh Mesh topology (OPEN-5)
[ ] Capability matrix in Mesh tab (OPEN-6)
[ ] Routing trace badge in Ask tab (OPEN-7)
[ ] E2E encryption on by default for chat (M23 wired but inactive)
[ ] Real LoRa hardware integration (M29 stub → serial port)
```

---

## Summary Table

| Item | Status | Impact |
|------|--------|--------|
| FIX-1 `_started` flag | ✅ Done | stop() now works; no double-start |
| FIX-2 chat exception swallowing | ✅ Done | Failures visible in logs |
| FIX-3 UTC=UTC duplicates | ✅ Done | Code quality |
| FIX-4 corpora_dir default | ✅ Done | Corpus writes to correct location |
| FIX-5 seed corpus not ingested | ✅ Done | Emergency knowledge base works |
| FIX-6 sticky session leak | ✅ Done | Long-lived nodes safe |
| FIX-7 app.py corpora_dir | ✅ Done | HF Space corpus in data dir |
| OPEN-1 relay hub persistence | ✅ Done | SQLite roster survives restart |
| OPEN-2 node.start() in app.py | ✅ Done | Local mDNS + HTTP transport active |
| OPEN-3 event_log injection | ✅ Done | Chat/Marketplace persist locally |
| OPEN-4 token expiry | ✅ Done | exp claim checked in handle_call() |
| OPEN-5 auto-refresh topology | ✅ Done | Mesh tab refreshes every 10 s |
| OPEN-6 capability matrix | ✅ Done | Already in get_mesh() JSON output |
| OPEN-7 routing trace badge | ✅ Done | 🏠/🌐 badge replaces raw JSON |
| Doc folder ingestion | ✅ Done | docs/guides/ + assets/initial_docs/ |
| P1 demo video | ⬜ CRITICAL | All prizes blocked without it |
| P2 social post | ⬜ CRITICAL | Best Demo badge |
| P3 NVIDIA_API_KEY | ⬜ HIGH | RTX 5080 prize |
