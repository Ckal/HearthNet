# M27 — MoE Expert Routing

**Spec version:** v3.0 — *experimental*
**Depends on:** [M03 Capability Bus](../../modules/M03-capability-bus.md), [M04 LLM](../../modules/M04-llm.md), [M10 Chat](../../modules/M10-chat.md), [M25 Group Chat](../../phase-2/modules/M25-group-chat.md), [X02 Event Log](../../cross-cutting/X02-events.md), [M16 Tokens](../../phase-2/modules/M16-tokens.md)
**Depended on by:** Optional routing layer in M03 Bus dispatcher

---

## 1. Responsibility

"MoE" here means **Mixture of Experts** in a generalised sense: given a question, route to the best expert. The experts can be:

- a **model** running locally on some node ("Llama-3.2-3B is good at code"),
- a **service** capability ("the niederrhein-emergency RAG corpus knows this"),
- a **human** with declared expertise ("Maria in Issum has organised Sankt Martins for 20 years"),
- an **external** API or another community via federation.

The router takes a query summary + tags, asks "which expert would do this best", returns top-K candidates with scores. The caller chooses one (or the system chooses automatically with a confidence threshold) and the chosen expert serves the request.

This module is a research bet that **knowing-who-to-ask is more valuable than scaling-the-model**. A 3B model that knows when to defer to a neighbour with first-hand knowledge will outperform a 70B model that has to confabulate. Whether that bet pays off is exactly what the research is for.

---

## 2. Non-goals

- **Auction-style routing.** Experts do not bid; there is no money flowing. Routing is by score, not price.
- **Mandatory routing.** The router is a *recommender*. The caller can always choose to run a query against a default LLM. MoE routing is opt-in per capability or per call.
- **Replacing RAG.** RAG still does retrieval inside a corpus. The router decides *which corpus* (or which non-RAG expert) — different layer.
- **Routing without consent.** A human expert never gets pinged unless they have explicitly registered availability for the topic.

---

## 3. File layout

```
hearthnet/moe/
├── __init__.py
├── router.py             # MoeRouter — the capability handler
├── scorer.py             # Learned scoring model; rule-based fallback
├── expert_registry.py    # Tracks registered experts and their declared topics
├── human_in_the_loop.py  # Coordinates handoff to a human; manages timeouts
└── feedback.py           # Records routing outcomes to train the scorer
```

---

## 4. Public API

### 4.1 Dataclasses

```python
@dataclass(frozen=True)
class ExpertDescriptor:
    expert_id:      ExpertID            # "human:<NodeID>" | "model:<id>" | "service:<cap_name>" | "external:<url>"
    kind:           ExpertKind
    topics:         frozenset[str]
    capabilities:   frozenset[str]      # for kind=service: which bus capability to invoke
    availability:   AvailabilityWindow
    consent_to_route: bool
    score_bias:     float = 0.0         # operator nudge; positive favours, negative dispels
    registered_at:  datetime
    expires_at:     datetime | None

@dataclass
class RouteCandidate:
    expert_id:      ExpertID
    kind:           ExpertKind
    score:          float
    expected_latency_minutes: int       # for humans, hours; for models, seconds
    rationale:      str
    name:           str | None          # for display

@dataclass
class RouteResult:
    candidates:     list[RouteCandidate]
    rationale:      str
    routed_at:      datetime

@dataclass
class Handoff:
    handoff_id:     str
    expert_id:      ExpertID
    context_summary: str
    initiated_at:   datetime
    deadline_at:    datetime
    state:          Literal["pending","accepted","declined","completed","timed_out"]
    thread_id:      ThreadID | None
```

### 4.2 `MoeRouter`

```python
class MoeRouter:
    """Capability handler for experimental.moe.route@1.0"""

    def __init__(
        self,
        bus:        CapabilityBus,
        registry:   ExpertRegistry,
        scorer:     Scorer,
        feedback:   FeedbackStore,
        settings:   MoeSettings,
        observability: Observability,
    ): ...

    async def start(self) -> None: ...

    async def route(self, body: RouteBody) -> RouteResult: ...
    async def handoff(self, body: HandoffBody) -> Handoff: ...
    async def feedback_outcome(self, handoff_id: str, outcome: Outcome) -> None: ...
```

### 4.3 `Scorer`

```python
class Scorer(Protocol):
    name: str

    def score(
        self,
        request_summary: str,
        tags:            list[str],
        candidates:      list[ExpertDescriptor],
        context:         ScoringContext,
    ) -> list[float]:
        """Return one score per candidate, same order."""
        ...

class RuleBasedScorer:
    """The default scorer.  Pure rules: tag overlap, recency of expert activity, availability, bias.  No ML."""
    ...

class LearnedScorer:
    """A small classifier trained on feedback outcomes.  Off by default; activated once
       MOE_ROUTER_TRAIN_MIN_EXAMPLES historical handoffs with outcomes are recorded."""
    ...
```

### 4.4 `ExpertRegistry`

```python
class ExpertRegistry:
    """
    Materialised view of `experimental.moe.expert.registered` events.
    Indexed by topic for fast routing.
    """

    def __init__(self, event_log: EventLog): ...

    def by_topic(self, tag: str) -> list[ExpertDescriptor]: ...
    def by_id(self, expert_id: ExpertID) -> ExpertDescriptor | None: ...
    def available_now(self) -> list[ExpertDescriptor]: ...
```

### 4.5 `HumanInTheLoopCoordinator`

```python
class HumanInTheLoopCoordinator:
    """
    Manages handoff-to-human flows.
    - Sends a chat invitation (M25 thread) to the chosen human.
    - Awaits acceptance within HANDOFF_RESPONSE_DEADLINE_MINUTES.
    - Falls back to next-best candidate if declined or timed out.
    - Stores audit trail (who routed where, why, outcome).
    """

    def __init__(self, bus: CapabilityBus, thread_service: ThreadService, registry: ExpertRegistry, settings: HitlSettings): ...

    async def initiate(self, handoff: Handoff) -> None: ...
    async def on_response(self, handoff_id: str, accepted: bool) -> None: ...
    async def on_completion(self, handoff_id: str, outcome: Outcome) -> None: ...
```

---

## 5. Behaviour

### 5.1 Expert registration

A node calls `experimental.moe.expert.register@1.0` to register an expert. For `kind="human"`:

- The caller must be the human in question (self-registration) OR be an anchor registering on behalf of a member with explicit consent token.
- `consent_to_route=true` is mandatory; humans without it are silently excluded from routing.
- Topics are free-form strings, lowercased, kebab-case. The registry will compute embeddings of topics so that `"sankt_martins"` and `"sankt martins"` match.

For `kind="model"` or `kind="service"`:

- The node hosting the model/service self-registers.
- Topics describe what the model is good at, e.g. `["code","python"]` or `["niederrhein-history","local-genealogy"]`.

For `kind="external"`:

- An anchor registers a third-party endpoint (HF Inference, OpenAI, Anthropic, another HearthNet community via federation).
- External experts are not consulted unless `policy.research.moe_allow_external=true`.

### 5.2 Routing flow

`experimental.moe.route@1.0`:

1. Caller submits `{request_summary, tags, top_k}`.
2. The registry returns all currently-available experts whose topics overlap `tags` or whose semantic similarity to `request_summary` is above `MOE_TOPIC_SIMILARITY_THRESHOLD` (default 0.55).
3. Scorer scores each candidate.
4. Apply score biases (per-expert operator nudges, per-community policy).
5. Sort descending; return top-K with rationales.
6. The caller decides whether to:
   - Route automatically (if top score ≥ `MOE_AUTO_ROUTE_THRESHOLD`, default 0.85),
   - Present the user with the candidate list to choose,
   - Or fall back to default LLM.

### 5.3 Handoff to a human expert

`experimental.moe.expert.handoff@1.0`:

1. The coordinator creates a new E2E group thread (M25) with the requester + chosen human.
2. The requester's question (or its summary) is posted to the thread.
3. The chosen human receives a notification.
4. If the human accepts within `HANDOFF_RESPONSE_DEADLINE_MINUTES` (default 60, configurable), the thread proceeds normally.
5. If declined or timed out: the coordinator silently picks the next candidate (or falls back to a model). The requester is informed once total wait exceeds `HANDOFF_WAIT_BUDGET_MINUTES` (default 30).

The human's UI shows handoffs as a low-priority "questions for you" inbox; they are not interruptive notifications by default. Policy can flip this for community types where instant response matters (e.g. civdef pilot, M31).

### 5.4 Routing model + RAG hybrid

A common pattern: a chat session begins, the user asks a question. The orchestrator:

1. Sends `request_summary` (the question + recent thread context) to the router.
2. If the top expert is a `service` expert pointing at `rag.query@1.0` against a specific corpus → run RAG against that corpus.
3. If the top is a `model` expert → run `llm.chat` against that model.
4. If the top is a `human` expert and the user explicitly opted in to human handoff → initiate handoff.
5. Else default model.

This is opt-in; the chat UI surfaces a "ask a neighbour?" affordance when human handoff is a credible option.

### 5.5 Feedback loop

After every routed call, the caller (or a UI signal: "did this answer your question?") records an `Outcome`:

```python
@dataclass
class Outcome:
    handoff_id:     str
    helpful:        bool | None            # None if no signal
    user_rating:    int | None             # 1–5
    completion_time_seconds: float | None
    handed_off_again: bool                 # the user asked the question elsewhere
```

Feedback is stored in `FeedbackStore` (SQLite). Once `MOE_ROUTER_TRAIN_MIN_EXAMPLES` (default 200) outcomes exist, the `LearnedScorer` becomes available and is retrained every `MOE_ROUTER_RETRAIN_EVERY_HOURS` (default 24). Communities can flip back to `RuleBasedScorer` at any time.

### 5.6 Privacy in routing

Routing is **observable** by definition — the request summary is sent to the router, which inspects it to pick an expert. Implications:

- The router lives on the **caller's own node**; the request summary is not transmitted off-node for routing.
- When the chosen expert is on a different node, the request body is sent over the bus as usual (signed, optionally E2E if it's a chat thread).
- The router does not log full request summaries. It logs `tags`, the candidate list, and the chosen expert. The summary is held in memory for the duration of the call.
- For handoff to humans, the human sees the actual question — they need to. The handoff event in the audit trail records "request handed off to X", not the question's content.

### 5.7 Cross-community routing (federation)

A federation manifest can include the scope `moe.route@1.0`. In that case the router can include experts from federated communities in its candidate list. Cross-community handoff:

- Initiates a federated thread (M25 + M14): the thread's events are bridged to the federated community.
- The expert's identity (e.g. "Lukas from Geldern") is visible to the requester.
- Federation scope must include `chat.thread.send@1.0` and `chat.thread.history@1.0` for the thread to function.

### 5.8 Operational policy

Communities can configure:

```yaml
moe:
  enabled: true
  auto_route_threshold: 0.85
  topic_similarity_threshold: 0.55
  human_handoff:
    enabled: true
    response_deadline_minutes: 60
    wait_budget_minutes: 30
    allowed_during_quiet_hours: false   # no human pings 22:00–06:00 local
  external_experts: false
  cross_community: false
```

### 5.9 Anti-abuse

- **Rate limit per requester:** `MOE_REQUESTS_PER_USER_PER_HOUR` (default 60). Prevents one user from spamming the human-expert pool.
- **Per-expert cooldown:** an expert is not offered the same user's request within `MOE_PER_EXPERT_COOLDOWN_MINUTES` (default 30).
- **Decline penalty:** an expert who declines 3 handoffs in a row gets temporarily marked `availability=false` until they update their registration.

---

## 6. Errors

| Code | Cause |
|------|-------|
| `experimental_disabled` | Research not enabled |
| `bad_request` | Empty `request_summary`, malformed tags |
| `not_found` | `expert_id` does not exist (in `handoff`) |
| `handoff_declined` | Chosen expert declined and no fallback was permitted |
| `handoff_timed_out` | No response within deadline |
| `policy_violation` | Cross-community handoff but federation does not allow |

---

## 7. Configuration

```toml
[research.moe]
enabled                       = false
scorer                        = "rule_based"   # "rule_based" | "learned"
auto_route_threshold          = 0.85
topic_similarity_threshold    = 0.55
top_k_default                 = 3
requests_per_user_per_hour    = 60
per_expert_cooldown_minutes   = 30
allow_external                = false
allow_cross_community         = false

[research.moe.human_handoff]
enabled                       = true
response_deadline_minutes     = 60
wait_budget_minutes           = 30
allowed_during_quiet_hours    = false
quiet_hours_start             = "22:00"
quiet_hours_end               = "06:00"

[research.moe.learned_scorer]
train_min_examples            = 200
retrain_every_hours           = 24
model_kind                    = "logistic_regression"   # small, interpretable
```

---

## 8. Tests

### 8.1 Unit
- RuleBasedScorer: tag-overlap dominance test (4 candidates, exact tag match scores highest)
- Availability filter: expert with `availability` window not covering "now" is excluded
- Cooldown: same user calls twice within `per_expert_cooldown_minutes` → second call excludes that expert

### 8.2 Integration
- Three-node community: two humans + one model registered as experts for `{cooking, niederrhein-history}`. Query about Sankt-Martins-Lieder → human expert chosen; handoff flow completes.
- Handoff decline: chosen expert declines, fallback picks next candidate; user sees a single thread experience without knowing about the decline.
- Cross-community: federation manifest grants `moe.route`; query routed to an expert in the federated community; thread bridged correctly.

### 8.3 Adversarial
- Spam: one user submits 100 routes in 10 minutes → rate-limit blocks at #60, returns `too_many_requests`.
- Decline-storm: an expert declines 10 in a row → after the third, that expert is auto-unavailable; not offered as candidate until they re-register.
- Score injection: a community member tries to set `score_bias=999` on their own expert record → registration rejects (caller must be anchor for `score_bias` outside `[-1, 1]`).

### 8.4 UX
- Top-K presentation in chat UI: candidates show as a 3-button affordance under the user's question; user picks one; thread morphs accordingly.
- Outcome capture: thumbs-up/down on the answer records an `Outcome`; visible in router metrics dashboard.

---

## 9. Cross-references

- Capability spec: [CAPABILITY_CONTRACT_v3 §4.4–4.6](../CAPABILITY_CONTRACT_v3.md)
- Group chat (handoff substrate): [M25](../../phase-2/modules/M25-group-chat.md)
- Federation: [M14](../../phase-2/modules/M14-federation.md)

---

## 10. Open research questions

1. **What signal predicts a good route?** Tag overlap is shallow. Embeddings of past handoffs vs current request might do better. The `LearnedScorer` is the placeholder; the actual feature engineering is unsolved.
2. **Calibration.** Is a score of 0.85 actually 85% likely to be a good route? Reliability diagrams from feedback data needed.
3. **Negative experts.** Should the router learn that "Llama-3.2 is *bad* at Niederrhein-Plattdeutsch" and avoid it? Currently only positive scores.
4. **Cold-start.** A new community has no feedback data and no `LearnedScorer`. Bootstrapping by federation (borrowing experts from a more-mature peer)?
5. **Human consent UX.** What is the right number of handoffs per week before it becomes a burden? Per-person ceiling, per-community ceiling, dynamic?
6. **Privacy of the rationale.** Should the rationale ("Maria worked on Sankt Martins for 20 years") be visible to the requester? It can reveal information about Maria. Default: rationale is shown to requester only when the expert opts in to that.
7. **Refusal protocol.** When a model expert "refuses" (e.g. "I cannot answer this"), should the router re-route, or trust the refusal? Mistaken refusals are a known LLM failure mode.
8. **Expert overlap.** Two experts both register for `{sankt_martins}`. Both equally good. What's the tiebreaker that doesn't always favour the same person? Round-robin? Random? Both score 0.85 — caller chooses?
9. **Network effects.** As more people register as experts, does the score signal get diluted? Empirical question.
10. **Audit and review.** A community might want a quarterly "who was routed to most, on what topics" view — for fairness, for spotting overworked experts. UX for surfacing this respectfully.
