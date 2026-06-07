# M08 — UI (Gradio Dashboard + Mobile Client)

**Spec version:** v1.0
**Depends on:** M03 (bus, the ONLY data source the UI talks to), X03 (observability, for trace display), X04 (config), M09 (emergency state subscribed), `gradio>=6.0.0`
**Depended on by:** M13 (onboarding extends the UI), M12 (CLI may launch UI)

The UI's strict rule: **it never imports a service module**. Every piece of data comes via `bus.call(...)` or via the bus's introspection APIs (`topology_snapshot`, `recent_traces`). This keeps the UI swappable.

---

## 1. Responsibility

Present a local-host web UI at `http://127.0.0.1:7860` showing:

- Live topology of the mesh
- An "ask" pane wired to `llm.chat` + `rag.query`
- A chat tab for direct messages
- A marketplace tab
- A files tab
- An emergency tab (visible only when offline)
- A settings tab
- A mobile web client served at `/mobile`

---

## 2. File layout

```
hearthnet/ui/
├── __init__.py
├── app.py                  # build_ui(): assembles Gradio Blocks
├── topology.py             # Cytoscape.js-backed topology component
├── theme.py                # Colour tokens, fonts, CSS
├── onboarding.py           # M13 owns this; reachable from settings
├── tabs/
│   ├── __init__.py
│   ├── ask.py              # LLM passthrough with optional RAG
│   ├── chat.py             # direct messages
│   ├── marketplace.py
│   ├── files.py
│   ├── emergency.py        # only mounted when offline state active
│   └── settings.py
└── mobile/                 # served as static at /mobile
    ├── index.html
    ├── app.js
    └── style.css
```

---

## 3. Public API

### 3.1 `app.py`

```python
# hearthnet/ui/app.py
import gradio as gr

class UiApp:
    def __init__(
        self,
        bus: CapabilityBus,
        state_bus: StateBus,                # M09
        config: UiConfig,
        node_id_short: str,
        community_name: str,
    ):
        ...

    def build(self) -> gr.Blocks:
        """Assemble the full UI."""

    async def launch_async(self) -> None:
        """Non-blocking launch. Used by node.py."""

    async def shutdown(self) -> None: ...

def build_ui(bus, state_bus, config, **meta) -> UiApp:
    """Convenience constructor used by node.py."""
```

### 3.2 `topology.py`

```python
# hearthnet/ui/topology.py
class TopologyComponent:
    """Wraps Cytoscape.js inside a Gradio HTML component.
       Auto-refreshes from bus.topology_snapshot() every 2s.
       Animates recent trace events (last 10s) along edges."""

    def __init__(self, bus: CapabilityBus): ...

    def render(self) -> gr.HTML: ...

    def push_trace(self, event: CallTraceEvent) -> None:
        """Trigger an edge animation. Color by capability prefix."""

    def push_topology(self, snapshot: TopologySnapshot) -> None: ...

# Cytoscape config:
# - Nodes: one per known peer + one for self
# - Edges: dynamic; appear on trace events; fade after 5s
# - Edge colour:  llm.*=teal,  rag.*=purple,  file.*=amber,
#                 chat.*=blue, market.*=green, community.*=grey
# - Node colour:  online=green, stale=amber, offline=red
# - Node label:   display_name + capability badges
# - On node click: side panel shows full manifest
```

---

## 4. Composition

The Gradio Blocks tree:

```
gr.Blocks(theme=hearthnet_theme, title="HearthNet")
├── header bar
│   ├── community name + node display name
│   ├── status pill (online/offline) → bound to state_bus
│   └── settings gear
├── topology pane (always visible at top)
└── tabs:
    ├── Ask          (always)
    ├── Chat         (always; badge with unread count)
    ├── Marketplace  (always)
    ├── Files        (always)
    ├── Notfall      (visible only when state.mode != "online")
    └── Settings     (always; includes Onboarding entry point)
```

---

## 5. Tabs

### 5.1 Ask tab — `tabs/ask.py`

A simple chat interface:

- Top: Corpus selector (dropdown, populated via `bus.call("rag.list_corpora", ...)`)
- Top right: Model selector (capabilities from `bus.topology_snapshot().capabilities_*` filtered by name=`llm.chat`)
- Centre: Chat history (Gradio Chatbot)
- Bottom: Input + Send

Behaviour on send:

```
1. if corpus selected:
   chunks = bus.call("rag.query", (1,0), {params:{corpus}, input:{query:msg, k:5}})
   build system prompt with chunks + sources
2. messages = [system_with_chunks, ...history, user_msg]
3. stream = bus.stream("llm.chat", (1,0), {params:{model}, input:{messages, stream:true}})
4. accumulate tokens into a streaming response in the Chatbot
5. on done: append sources panel (clickable to open file)
```

### 5.2 Settings tab — `tabs/settings.py`

- Node identity (read-only)
- Community membership (read-only; "leave community" with double-confirm)
- LLM backend list (read-only; edit via config.toml)
- Theme toggle (Hearth / Spark dark mode)
- Debug toggles (verbose logging, trace ring buffer dump)
- Onboarding entrypoints: "Create new community", "Join via invite"
- Privacy: "Erase all data" (triple-confirm, wipes keys + state)

### 5.3 Chat tab — `tabs/chat.py`

- Left: peer list with last-message timestamps, unread badges
  - Source: `bus.call("chat.history", (1,0), {input:{}})` → group by peer
- Right: message thread for selected peer
  - Auto-refresh on local pubsub topic `chat.message.<our_short_id>`
- Bottom: input + send + attachment button (opens file picker → uploads as blob via `file.put` → attaches CID)
- "Encrypted" indicator placeholder (Phase 2)

### 5.4 Marketplace tab — `tabs/marketplace.py`

- Top: Category filter, tag filter, search box (semantic)
- Centre: Cards (one per post)
- Bottom-right: "Neuer Beitrag" → modal for new post
- "Mark fulfilled" / "Withdraw" on each card if author == us

### 5.5 Files tab — `tabs/files.py`

- Left: corpus / pinned / recent
- Centre: file grid
- Upload area at top
- Click: preview (image / PDF / text), download, advertise to peers

### 5.6 Emergency tab — `tabs/emergency.py`

Visible only when `state_bus.current().mode != "online"`. Designed for big buttons, low-stress reading. Large amber banner at top.

Contents:

- Big "Was tun?" button → opens the most relevant corpus (default `niederrhein-emergency`)
- Neighbour list (last seen times prominent)
- Direct chat shortcut
- "Update" indicator: how far behind the event log we are vs. last sync
- Shared resources table (generator availability, water, light) — Phase 2

### 5.7 Banner

```
INTERNET OFFLINE — LOKAL AKTIV
seit 14:32 · 3 Nachbar*innen erreichbar
```

When degraded:
```
EINGESCHRÄNKTE VERBINDUNG · Lokale Dienste aktiv
```

---

## 6. Mobile client (`mobile/`)

Plain static HTML + JS, no framework. Served by [X01](../cross-cutting/X01-transport.md) at `/mobile/*`. Same bus API (signed requests, but credentials stored in `IndexedDB`).

Minimum features:
- Ask (LLM passthrough)
- Chat
- Marketplace browse
- Emergency mode banner
- No topology viz (too dense for small screen)

Auth on mobile: the user scans an invite QR with the camera → key derived in WebCrypto → stored in IndexedDB.

---

## 7. Theming (`theme.py`)

Two themes:

- **Hearth (default)** — warm, parchment background, dark walnut accents
- **Spark (high-contrast / dark)** — black bg, amber accents — also the emergency theme

CSS variables:

```css
--hn-bg:         #f4ead7;  /* hearth */
--hn-bg-dark:    #1a1816;  /* spark */
--hn-accent:     #b45309;  /* amber */
--hn-accent-2:   #14b8a6;  /* teal */
--hn-accent-3:   #6d28d9;  /* purple, used for rag */
--hn-text:       #2c1810;
--hn-text-dark:  #f4ead7;
--hn-error:      #b91c1c;
--hn-warn:       #d97706;
--hn-ok:         #15803d;
```

When emergency mode is active, theme switches to Spark with amber accents and the banner.

---

## 8. Behaviour

### 8.1 Topology refresh

Every 2 s the topology component calls `bus.topology_snapshot()`. Diff with previous; only changed nodes/edges trigger re-render. Trace ring is read via `bus.recent_traces(50)` every 1 s and pushed as animations.

### 8.2 Live updates without polling

Where possible the UI subscribes:

- `state_bus.subscribe()` for emergency banner
- `bus.registry.subscribe()` for topology pane (additive)
- Pubsub `marketplace.post.created` for marketplace tab live refresh
- Pubsub `chat.message.<our_short_id>` for chat tab notifications

### 8.3 Error display

- Capability call errors → toast at top with code and "details" expander
- Backend warm-up takes time → spinner with "Modell wird geladen ..."
- Network failures during a stream → frame "verbindung abgerissen" injected; user can retry

### 8.4 Settings persistence

Settings tab edits go to `config.toml` via [X04 §3](../cross-cutting/X04-config.md). Some require restart; UI clearly indicates this.

### 8.5 First-run handoff to M13

If on startup `config.community.community_id is None`, the UI redirects to onboarding (see [M13](M13-onboarding.md)) instead of showing tabs.

---

## 9. Configuration

From [X04 §3](../cross-cutting/X04-config.md):

```python
config.ui.host             # 127.0.0.1
config.ui.port             # 7860
config.ui.launch_browser   # auto-open in browser on launch
```

---

## 10. Tests

### Unit
- `test_theme_tokens_present`
- `test_emergency_tab_hidden_when_online`
- `test_emergency_tab_shown_when_offline`
- `test_topology_diff_avoids_unchanged_render` (mock bus)
- `test_settings_writes_to_config_file_atomically`

### Integration
- `test_ask_tab_does_rag_then_llm_in_order` — mock bus, observe call sequence
- `test_marketplace_tab_refreshes_on_pubsub_event`
- `test_mobile_endpoint_serves_index_html`

### Manual
- Demo dry-run script: open UI, type query, observe topology animation, unplug WAN, observe banner ≤ 5s. Document in `tests/demo_script.md`.

---

## 11. Cross-references

| What | Where |
|------|-------|
| Bus introspection APIs | [M03 §3.7](M03-bus.md) |
| Emergency state source | [M09 §3.1](M09-emergency.md) |
| Pubsub topics | [CONTRACT §8](../CAPABILITY_CONTRACT.md) |
| Onboarding flow | [M13](M13-onboarding.md) |
| Mobile served by | [X01 §3.2](../cross-cutting/X01-transport.md) |
| Trace event format | [M03 §3.6](M03-bus.md) |

---

## 12. Open questions

1. **Gradio version compatibility** — Gradio 6.x evolves quickly. Pin a minor.
2. **Native mobile** — Phase 2 (Flutter or React Native). Web works for hackathon.
3. **Accessibility** — colour contrast meets WCAG AA in both themes; not yet audited.
4. **Internationalisation** — UI strings in German + English. Switchable. Plattdeutsch as a stretch.
5. **Cytoscape vs D3** — Cytoscape preferred (less code). Performance budget: 50 nodes, 500 edges.
