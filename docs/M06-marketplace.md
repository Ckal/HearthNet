# M06 — Marketplace Service

**Spec version:** v1.0
**Depends on:** M01 (identity, for signed events), M03 (bus), X02 (events, for storage + replay), X04 (config), X03 (observability), optionally M11 (embedding, for `market.search`)
**Depended on by:** M08 (UI marketplace tab)

---

## 1. Responsibility

Provide `market.list`, `market.post`, `market.expire`, `market.search` capabilities. Maintain a materialised view of current (non-expired) posts derived from the community event log.

The marketplace is **event-sourced**: posts are not stored as a table the service writes to. They are derived from `market.post.*` events in the X02 log. This makes posts automatically signed, durable, and gossipable.

---

## 2. File layout

```
hearthnet/services/marketplace/
├── __init__.py
├── service.py        # MarketplaceService
├── post.py           # Post dataclass + helpers
└── views.py          # MarketplaceView: MaterialisedView from X02
```

---

## 3. Public API

### 3.1 `post.py`

```python
# hearthnet/services/marketplace/post.py
from dataclasses import dataclass
from typing import Literal

Category = Literal["offer", "request", "info", "emergency"]

@dataclass(frozen=True)
class Location:
    lat:   float
    lng:   float
    label: str

@dataclass(frozen=True)
class Post:
    """The marketplace's domain object.
       Derived from a market.post.created event + zero or more market.post.updated events,
       and terminated by a market.post.expired event."""
    event_id:   str           # ULID of the original .created event
    lamport:    int
    author:     str           # NodeID full form
    category:   Category
    title:      str
    body:       str
    location:   Location | None
    tags:       list[str]
    created_at: str
    expires_at: str
    expired_via_event_id: str | None      # set when expired
    expiry_reason: str | None              # "fulfilled" | "withdrawn" | ...

    def is_expired(self, now: datetime | None = None) -> bool: ...
```

### 3.2 `views.py`

```python
# hearthnet/services/marketplace/views.py
class MarketplaceView:
    """MaterialisedView (X02 protocol).
       Subscribes to event_types: market.post.created, .updated, .expired."""

    def __init__(self): ...

    # MaterialisedView protocol:
    def reset(self) -> None: ...
    def apply(self, event: Event) -> None: ...
    def snapshot_state(self) -> dict: ...
    def restore_state(self, state: dict) -> None: ...

    # queries used by the service handlers:
    def list(
        self,
        *,
        category: Category | None = None,
        tags: list[str] | None = None,
        since_lamport: int = 0,
        limit: int = 50,
    ) -> list[Post]: ...

    def get(self, event_id: str) -> Post | None: ...
    def max_lamport(self) -> int: ...

    # bulk listings for search:
    def all_active(self) -> list[Post]: ...
```

### 3.3 `service.py`

```python
# hearthnet/services/marketplace/service.py
class MarketplaceService:
    name    = "marketplace"
    version = "1.0"

    def __init__(
        self,
        config: MarketConfig,
        bus: CapabilityBus,
        event_log: EventLog,
        replay_engine: ReplayEngine,
        author_kp: KeyPair,            # this node's key, for signing posts
        community_manifest_provider: Callable[[], CommunityManifest],
    ):
        self.view = MarketplaceView()
        replay_engine.register(
            "marketplace",
            self.view,
            event_types=["market.post.created", "market.post.updated", "market.post.expired"],
        )

    def capabilities(self) -> list[tuple[CapabilityDescriptor, Callable, ParamsPredicate]]:
        """Registers: market.list, market.post, market.expire, market.search."""

    async def start(self) -> None:
        """Replay relevant events into the view; install background sweeper for auto-expiry."""

    async def stop(self) -> None: ...
    def health(self) -> dict: ...

    # --- handlers ---

    async def handle_list(self, req: RouteRequest) -> dict:
        """CONTRACT §4.11."""

    async def handle_post(self, req: RouteRequest) -> dict:
        """CONTRACT §4.12.
        Validates ttl ≤ config.market.max_ttl_seconds.
        Idempotency by client_id: if an event with matching (author, client_id) already exists, return its event_id.
        Otherwise: append market.post.created event via event_log.append_local."""

    async def handle_expire(self, req: RouteRequest) -> dict:
        """CONTRACT §4.13.
        Checks caller is original author OR trusted moderator.
        Appends market.post.expired event."""

    async def handle_search(self, req: RouteRequest) -> dict:
        """CONTRACT §4.14.
        1. bus.call('embed.text', (1,0), {texts: [query]})
        2. For each active post, embed (cached) and score via cosine.
        3. Return top-k.
        Cache embedding per (event_id, body+title hash)."""
```

### 3.4 Capability descriptors

```python
descriptor_list = CapabilityDescriptor(
    name="market.list", version=(1, 0), stability="stable",
    request_schema={...}, response_schema={...}, stream_schema=None,
    params={}, max_concurrent=8,
    trust_required="member", timeout_seconds=5, idempotent=True,
)

descriptor_post = CapabilityDescriptor(
    name="market.post", version=(1, 0), stability="stable",
    request_schema={...}, response_schema={...}, stream_schema=None,
    params={}, max_concurrent=4,
    trust_required="member", timeout_seconds=10, idempotent=True,
)

descriptor_expire = CapabilityDescriptor(
    name="market.expire", version=(1, 0), stability="stable",
    request_schema={...}, response_schema={...}, stream_schema=None,
    params={}, max_concurrent=4,
    trust_required="member", timeout_seconds=5, idempotent=True,
)

descriptor_search = CapabilityDescriptor(
    name="market.search", version=(1, 0), stability="stable",
    request_schema={...}, response_schema={...}, stream_schema=None,
    params={}, max_concurrent=4,
    trust_required="member", timeout_seconds=10, idempotent=True,
)
```

All four use the default `lambda offered, requested: True` params predicate.

---

## 4. Behaviour

### 4.1 Event-sourcing in practice

```
client → market.post (via bus)
  ↓
service.handle_post
  → validate
  → idempotency check on (author, client_id)
  → event_log.append_local("market.post.created", data, author_kp)
  → X02 fans out the new event to ReplayEngine
  → MarketplaceView.apply(event) updates in-memory state
  → service returns {event_id, lamport}
```

```
peer sync brings remote market.post.created event
  ↓
event_log.append_received(event)
  → ReplayEngine triggers MarketplaceView.apply(event)
  → next market.list call sees the new post
```

The service NEVER writes posts directly. The event log is the only mutator.

### 4.2 Auto-expiry sweeper

Background task scanning the view every 60 seconds:

- For each post where `now >= expires_at` AND no `.expired` event seen: append `market.post.expired` event with reason `"stale"` and the local node as author.
- This is best-effort; only the post's author or a trusted member is supposed to expire it, but for "stale" reason, any anchor MAY do it.

Conflict: if two nodes auto-expire concurrently, both events land, view de-duplicates by `target_event_id`. Last-writer-wins per Lamport (no functional difference — both say "expired").

### 4.3 Search caching

Embedding all active posts on every search is wasteful. Cache strategy:

- Per-post embedding cached in memory keyed by `(event_id, hash(title+body))`
- On `.updated` event, invalidate
- Cache size bounded; LRU eviction at 5000 entries

Phase 1.5 optimisation. MVP may re-embed each time.

### 4.4 Trust check for expire

```python
def can_expire(caller_node_id, post, reason, community_manifest):
    if caller_node_id == post.author:
        return True
    if reason in ("fulfilled", "withdrawn", "user_request"):
        return caller_node_id == post.author   # author-only for these reasons
    if reason == "stale":
        return community_manifest.level_of(caller_node_id) in ("trusted", "anchor")
    return False
```

### 4.5 Categories vs tags

- `category` is a fixed enum (4 values)
- `tags` are free-form, sourced from user input; the UI presents popular tags as suggestions

### 4.6 Geofencing

`location` is advisory. Display only. No filtering in MVP. Phase 2: `market.list` filter on distance.

---

## 5. Composition with `market.search`

```
UI input: "wasser notfall"
  ↓
bus.call("market.search", (1,0), {input: {query: "wasser notfall", k: 10}})
  → MarketplaceService.handle_search
       → bus.call("embed.text", (1,0), {texts: ["wasser notfall"]})
       → score each active post (cached embedding) → top-k
       → return posts with scores
```

The marketplace service depends on `embed.text` being available somewhere on the mesh. If embedding is unavailable, search falls back to substring matching (logged at `warning`).

---

## 6. Errors

| Condition | Wire code |
|-----------|-----------|
| ttl_seconds > max_ttl_seconds | `bad_request` |
| caller not authorised to expire | `unauthorized` |
| target post not found (expire/update) | `not_found` |
| no embedding provider for search | `partition` (degrades to substring) |

---

## 7. Configuration

From [X04 §3](../cross-cutting/X04-config.md):

```python
config.market.enabled
config.market.default_ttl_seconds   # 7 days
config.market.max_ttl_seconds       # 30 days
```

---

## 8. Tests

### Unit
- `test_post_event_appears_in_view_after_apply`
- `test_post_is_idempotent_on_client_id`
- `test_expire_unauthorized_caller_rejected`
- `test_auto_expire_appends_event_with_stale_reason`
- `test_replay_then_snapshot_then_restore_equal_state`
- `test_search_falls_back_to_substring_when_embedding_unavailable`

### Integration
- `test_two_node_post_visible_after_sync`
- `test_three_node_concurrent_posts_all_visible`
- `test_expire_propagates_then_list_excludes`
- `test_market_search_returns_relevant`

---

## 9. Cross-references

| What | Where |
|------|-------|
| `market.*` wire | [CONTRACT §4.11–4.14](../CAPABILITY_CONTRACT.md) |
| Event types | [CONTRACT §7.2](../CAPABILITY_CONTRACT.md) |
| Event log | [X02](../cross-cutting/X02-events.md) |
| Embed via bus | [M11](M11-embedding.md) |
| UI marketplace tab | [M08 §5.4](M08-ui.md) |

---

## 10. Open questions

1. **Geographic filter** — Phase 2 with a `location_filter: {center, radius_km}`.
2. **Moderation tooling** — a "report" flow with admin queue; Phase 2.
3. **Inter-community marketplace federation** — Phase 2 / 3.
4. **Encryption of post bodies** — currently cleartext within community. Could encrypt at-rest in event log. Out of scope.
