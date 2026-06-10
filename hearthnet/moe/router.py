"""M27 — MoE Expert Routing (experimental, Phase 3).

Routes queries to the best expert: local model, service capability, human, or external.
Gated by config.research.moe_routing = True.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field

ExpertID = str
ThreadID = str


@dataclass(frozen=True)
class ExpertDescriptor:
    """Describes an available expert (model, service, human, or external)."""

    expert_id: ExpertID  # "human:<NodeID>" | "model:<id>" | "service:<cap>" | "external:<url>"
    expert_type: str  # "human" | "model" | "service" | "external"
    topic_tags: frozenset[str]
    confidence_score: float  # 0.0-1.0, self-reported
    community_id: str
    name: str | None = None
    description: str | None = None
    expires_at: float | None = None

    def is_expired(self, now: float | None = None) -> bool:
        if self.expires_at is None:
            return False
        return (now or time.time()) > self.expires_at


@dataclass
class RouteCandidate:
    expert_id: ExpertID
    score: float
    reason: str
    expert_type: str
    name: str | None = None


@dataclass
class RouteResult:
    candidates: list[RouteCandidate]
    query_summary: str
    routed_at: float = field(default_factory=time.time)


@dataclass
class Handoff:
    """A pending handoff to a human expert."""

    handoff_id: str
    expert_id: ExpertID
    query: str
    created_at: float = field(default_factory=time.time)
    resolved_at: float | None = None
    status: str = "pending"  # "pending" | "accepted" | "declined" | "timeout"
    thread_id: ThreadID | None = None


class ExpertRegistry:
    """Tracks registered experts and their declared topics."""

    def __init__(self) -> None:
        self._experts: dict[ExpertID, ExpertDescriptor] = {}

    def register(self, descriptor: ExpertDescriptor) -> None:
        self._experts[descriptor.expert_id] = descriptor

    def unregister(self, expert_id: ExpertID) -> bool:
        if expert_id in self._experts:
            del self._experts[expert_id]
            return True
        return False

    def list_active(self, now: float | None = None) -> list[ExpertDescriptor]:
        now = now or time.time()
        return [e for e in self._experts.values() if not e.is_expired(now)]

    def find_by_tags(self, tags: set[str], now: float | None = None) -> list[ExpertDescriptor]:
        active = self.list_active(now)
        return [e for e in active if e.topic_tags & tags]


class MoeRouter:
    """Recommends experts for a query.

    Uses a simple rule-based scorer in Phase 3.
    A learned scorer (embedding-based) is planned but not yet implemented.
    Only active when config.research.moe_routing = True.
    """

    def __init__(self, registry: ExpertRegistry | None = None, bus=None) -> None:
        self._registry = registry or ExpertRegistry()
        self._bus = bus
        self._pending_handoffs: dict[str, Handoff] = {}

    @property
    def registry(self) -> ExpertRegistry:
        return self._registry

    def route(self, query: str, top_k: int = 3, tags: set[str] | None = None) -> RouteResult:
        """Return top-K expert candidates for a query."""
        candidates_src = self._registry.list_active()
        if tags:
            candidates_src = [e for e in candidates_src if e.topic_tags & tags]

        # Simple scoring: exact tag matches + confidence weight
        query_words = set(query.lower().split())
        scored: list[RouteCandidate] = []
        for expert in candidates_src:
            tag_overlap = len(expert.topic_tags & query_words)
            score = expert.confidence_score * (1.0 + 0.2 * tag_overlap)
            scored.append(
                RouteCandidate(
                    expert_id=expert.expert_id,
                    score=min(score, 1.0),
                    reason=f"tag_overlap={tag_overlap}, confidence={expert.confidence_score:.2f}",
                    expert_type=expert.expert_type,
                    name=expert.name,
                )
            )

        scored.sort(key=lambda c: c.score, reverse=True)
        return RouteResult(
            candidates=scored[:top_k],
            query_summary=query[:200],
        )

    def initiate_handoff(
        self, expert_id: ExpertID, query: str, thread_id: str | None = None
    ) -> Handoff:
        """Create a pending handoff to a human expert."""
        h = Handoff(
            handoff_id=str(uuid.uuid4()),
            expert_id=expert_id,
            query=query,
            thread_id=thread_id,
        )
        self._pending_handoffs[h.handoff_id] = h
        return h

    def resolve_handoff(self, handoff_id: str, status: str) -> bool:
        if handoff_id in self._pending_handoffs:
            h = self._pending_handoffs[handoff_id]
            self._pending_handoffs[handoff_id] = Handoff(
                handoff_id=h.handoff_id,
                expert_id=h.expert_id,
                query=h.query,
                created_at=h.created_at,
                resolved_at=time.time(),
                status=status,
                thread_id=h.thread_id,
            )
            return True
        return False
