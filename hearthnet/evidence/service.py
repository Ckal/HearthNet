"""M30 — Evidence Graph bus service (experimental, Phase 3).

Wraps the real in-memory :class:`ClaimStore` as capability-bus handlers so the
content-addressed claim graph is reachable over the mesh. Registered only when a
node opts into research features (``install_extended_services(research=True)``).

Capabilities:
  evidence.claim.add@1.0      — assert a claim, returns its content-addressed id
  evidence.claim.attest@1.0   — vouch for an existing claim
  evidence.claim.dispute@1.0  — dispute an existing claim
  evidence.claim.find@1.0     — list claims about a subject
  evidence.summary@1.0        — store statistics
"""

from __future__ import annotations

from typing import Any

from hearthnet.bus.capability import CapabilityDescriptor, RouteRequest
from hearthnet.evidence.store import (
    Attestation,
    Claim,
    ClaimID,
    ClaimSource,
    ClaimStore,
    Dispute,
    SourceID,
)


class EvidenceService:
    name = "evidence"
    version = "1.0"

    def __init__(self, community_id: str = "", store: ClaimStore | None = None) -> None:
        self._community_id = community_id
        self._store = store or ClaimStore()

    def capabilities(self) -> list[tuple]:
        return [
            (
                CapabilityDescriptor(
                    name="evidence.claim.add",
                    version=(1, 0),
                    stability="experimental",
                    trust_required="trusted",
                    idempotent=True,
                ),
                self.handle_add,
                None,
            ),
            (
                CapabilityDescriptor(
                    name="evidence.claim.attest",
                    version=(1, 0),
                    stability="experimental",
                    trust_required="trusted",
                ),
                self.handle_attest,
                None,
            ),
            (
                CapabilityDescriptor(
                    name="evidence.claim.dispute",
                    version=(1, 0),
                    stability="experimental",
                    trust_required="trusted",
                ),
                self.handle_dispute,
                None,
            ),
            (
                CapabilityDescriptor(
                    name="evidence.claim.find",
                    version=(1, 0),
                    stability="experimental",
                    idempotent=True,
                ),
                self.handle_find,
                None,
            ),
            (
                CapabilityDescriptor(
                    name="evidence.summary",
                    version=(1, 0),
                    stability="experimental",
                    idempotent=True,
                ),
                self.handle_summary,
                None,
            ),
        ]

    def register(self, bus: Any) -> None:
        for cap, handler, predicate in self.capabilities():
            bus.register_capability(cap, handler, predicate)

    # ── Handlers ───────────────────────────────────────────────────────────

    async def handle_add(self, req: RouteRequest) -> dict:
        inp = req.body.get("input", {})
        subject = str(inp.get("subject", ""))
        predicate = str(inp.get("predicate", "asserts"))
        object_ = str(inp.get("object", ""))
        if not subject or not object_:
            return {"error": "bad_request", "message": "subject and object are required"}
        sources = tuple(
            ClaimSource(
                source_id=SourceID(str(s.get("source_id", ""))),
                source_type=str(s.get("source_type", "manual")),
                url=s.get("url"),
                reliability_score=float(s.get("reliability_score", 1.0)),
            )
            for s in inp.get("sources", [])
        )
        claim = Claim(
            claim_id=ClaimID(""),  # replaced by content_id() inside add_claim
            subject=subject,
            predicate=predicate,
            object_=object_,
            asserted_by=str(req.caller or "unknown"),
            sources=sources,
            community_id=self._community_id,
            confidence=float(inp.get("confidence", 1.0)),
        )
        cid = self._store.add_claim(claim)
        return {"output": {"claim_id": cid}, "meta": {}}

    async def handle_attest(self, req: RouteRequest) -> dict:
        inp = req.body.get("input", {})
        claim_id = ClaimID(str(inp.get("claim_id", "")))
        if self._store.get_claim(claim_id) is None:
            return {"error": "not_found", "message": "unknown claim_id"}
        self._store.attest(Attestation(claim_id=claim_id, attested_by=str(req.caller or "unknown")))
        return {
            "output": {
                "claim_id": claim_id,
                "attestations": self._store.attestation_count(claim_id),
            },
            "meta": {},
        }

    async def handle_dispute(self, req: RouteRequest) -> dict:
        inp = req.body.get("input", {})
        claim_id = ClaimID(str(inp.get("claim_id", "")))
        if self._store.get_claim(claim_id) is None:
            return {"error": "not_found", "message": "unknown claim_id"}
        counter = inp.get("counter_claim_id")
        self._store.dispute(
            Dispute(
                claim_id=claim_id,
                disputed_by=str(req.caller or "unknown"),
                reason=str(inp.get("reason", "")),
                counter_claim_id=ClaimID(str(counter)) if counter else None,
            )
        )
        return {"output": {"claim_id": claim_id, "disputed": True}, "meta": {}}

    async def handle_find(self, req: RouteRequest) -> dict:
        inp = req.body.get("input", {})
        subject = str(inp.get("subject", ""))
        claims = self._store.find_by_subject(subject)
        return {
            "output": {
                "claims": [
                    {
                        "claim_id": c.content_id(),
                        "subject": c.subject,
                        "predicate": c.predicate,
                        "object": c.object_,
                        "asserted_by": c.asserted_by,
                        "confidence": c.confidence,
                        "attestations": self._store.attestation_count(c.content_id()),
                        "disputed": self._store.is_disputed(c.content_id()),
                    }
                    for c in claims
                ]
            },
            "meta": {"count": len(claims)},
        }

    async def handle_summary(self, req: RouteRequest) -> dict:
        return {"output": self._store.summary(), "meta": {}}
