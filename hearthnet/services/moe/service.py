"""M27 — MoE Expert Routing service.

Wraps MoeRouter as a capability bus service.  Three capabilities:

  moe.route       — score all active experts for a query, return ranked list
  moe.register    — register an expert descriptor (model, service, human, external)
  moe.list        — list currently active experts

Gated by config.research.moe_routing = True in production; available
unconditionally when installed via node.install_services().
"""

from __future__ import annotations

import time

from hearthnet.bus.capability import CapabilityDescriptor, RouteRequest
from hearthnet.moe.router import ExpertDescriptor, ExpertRegistry, MoeRouter


class MoeService:
    """Bus service wrapping MoeRouter (M27).

    Registers moe.route, moe.register, moe.list on the capability bus.
    """

    name = "moe"
    version = "1.0"

    def __init__(self, bus=None) -> None:
        self._registry = ExpertRegistry()
        self._router = MoeRouter(registry=self._registry, bus=bus)
        self._bus = bus

    # ------------------------------------------------------------------
    # Capability registration
    # ------------------------------------------------------------------

    def capabilities(self) -> list[tuple]:
        return [
            (
                CapabilityDescriptor(
                    name="moe.route",
                    version=(1, 0),
                    stability="beta",
                    params={},
                    max_concurrent=16,
                    trust_required="member",
                    timeout_seconds=5,
                    idempotent=True,
                ),
                self.handle_route,
                None,
            ),
            (
                CapabilityDescriptor(
                    name="moe.register",
                    version=(1, 0),
                    stability="beta",
                    params={},
                    max_concurrent=8,
                    trust_required="member",
                    timeout_seconds=5,
                    idempotent=True,
                ),
                self.handle_register,
                None,
            ),
            (
                CapabilityDescriptor(
                    name="moe.list",
                    version=(1, 0),
                    stability="beta",
                    params={},
                    max_concurrent=16,
                    trust_required="member",
                    timeout_seconds=5,
                    idempotent=True,
                ),
                self.handle_list,
                None,
            ),
            (
                CapabilityDescriptor(
                    name="moe.handoff",
                    version=(1, 0),
                    stability="beta",
                    params={},
                    max_concurrent=4,
                    trust_required="trusted",
                    timeout_seconds=30,
                    idempotent=False,
                ),
                self.handle_handoff,
                None,
            ),
        ]

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    async def handle_route(self, req: RouteRequest) -> dict:
        """Route a query to the best experts.

        input:
          query: str           — the text to route
          top_k: int = 3       — number of experts to return
          tags: list[str] = [] — filter by topic tags (optional)

        output:
          candidates: list[{expert_id, score, reason, expert_type, name}]
          query_summary: str
          routed_at: float
        """
        inp = req.body.get("input", {})
        query = inp.get("query", "")
        top_k = int(inp.get("top_k", 3))
        tags: set[str] = set(inp.get("tags") or [])

        if not query:
            return {"error": "bad_request", "message": "query is required"}

        result = self._router.route(query, top_k=top_k, tags=tags or None)

        return {
            "output": {
                "candidates": [
                    {
                        "expert_id": c.expert_id,
                        "score": round(c.score, 4),
                        "reason": c.reason,
                        "expert_type": c.expert_type,
                        "name": c.name,
                    }
                    for c in result.candidates
                ],
                "query_summary": result.query_summary,
                "routed_at": result.routed_at,
            },
            "meta": {"expert_count": len(self._registry.list_active())},
        }

    async def handle_register(self, req: RouteRequest) -> dict:
        """Register an expert descriptor.

        input:
          expert_id: str           - "human:<NodeID>" | "model:<id>" | "service:<cap>"
          expert_type: str         - "human" | "model" | "service" | "external"
          topic_tags: list[str]    - topic tags for matching
          confidence_score: float  - 0.0-1.0 self-reported
          community_id: str
          name: str = ""
          description: str = ""
          ttl_seconds: float = 3600   - 0 = never expires
        """
        inp = req.body.get("input", {})
        expert_id = inp.get("expert_id", "")
        expert_type = inp.get("expert_type", "model")
        topic_tags = frozenset(inp.get("topic_tags") or [])
        confidence = float(inp.get("confidence_score", 0.5))
        community_id = inp.get("community_id", "")
        name = inp.get("name")
        description = inp.get("description")
        ttl = float(inp.get("ttl_seconds", 3600))

        if not expert_id:
            return {"error": "bad_request", "message": "expert_id is required"}

        expires_at = (time.time() + ttl) if ttl > 0 else None
        descriptor = ExpertDescriptor(
            expert_id=expert_id,
            expert_type=expert_type,
            topic_tags=topic_tags,
            confidence_score=min(1.0, max(0.0, confidence)),
            community_id=community_id,
            name=name,
            description=description,
            expires_at=expires_at,
        )
        self._registry.register(descriptor)

        return {
            "output": {
                "registered": True,
                "expert_id": expert_id,
                "expires_at": expires_at,
                "active_count": len(self._registry.list_active()),
            },
            "meta": {},
        }

    async def handle_list(self, req: RouteRequest) -> dict:
        """List active experts.

        output:
          experts: list[{expert_id, expert_type, topic_tags, confidence_score, name}]
          total: int
        """
        experts = self._registry.list_active()
        return {
            "output": {
                "experts": [
                    {
                        "expert_id": e.expert_id,
                        "expert_type": e.expert_type,
                        "topic_tags": list(e.topic_tags),
                        "confidence_score": e.confidence_score,
                        "community_id": e.community_id,
                        "name": e.name,
                        "description": e.description,
                        "expires_at": e.expires_at,
                    }
                    for e in experts
                ],
                "total": len(experts),
            },
            "meta": {},
        }

    async def handle_handoff(self, req: RouteRequest) -> dict:
        """Initiate a handoff to a human expert.

        input:
          expert_id: str
          query: str
          thread_id: str = None

        output:
          handoff_id: str
          expert_id: str
          status: "pending"
        """
        inp = req.body.get("input", {})
        expert_id = inp.get("expert_id", "")
        query = inp.get("query", "")
        thread_id = inp.get("thread_id")

        if not expert_id or not query:
            return {"error": "bad_request", "message": "expert_id and query are required"}

        handoff = self._router.initiate_handoff(expert_id, query, thread_id)
        return {
            "output": {
                "handoff_id": handoff.handoff_id,
                "expert_id": handoff.expert_id,
                "status": handoff.status,
                "created_at": handoff.created_at,
            },
            "meta": {},
        }
