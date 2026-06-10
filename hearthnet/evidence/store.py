"""M30 — Evidence Graph & EBKH Integration (experimental, Phase 3).

Content-addressed claim graph alongside the event log.
Events record what happened; claims record what is believed and by whom.
Gated by config.research.evidence_graph = True.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, NewType

ClaimID = NewType("ClaimID", str)
SourceID = NewType("SourceID", str)


@dataclass(frozen=True)
class ClaimSource:
    source_id: SourceID
    source_type: str  # "event" | "external" | "ebkh" | "manual"
    url: str | None = None
    retrieved_at: float | None = None
    reliability_score: float = 1.0


@dataclass(frozen=True)
class Claim:
    """An assertion by a node about some fact, with provenance."""

    claim_id: ClaimID
    subject: str  # what the claim is about (URI or free text)
    predicate: str  # what is being claimed
    object_: str  # the claimed value
    asserted_by: str  # NodeID of the asserting node
    sources: tuple[ClaimSource, ...]
    community_id: str
    asserted_at: float = field(default_factory=time.time)
    confidence: float = 1.0
    signature: bytes = b""

    def content_id(self) -> ClaimID:
        """Stable content-addressed ID based on subject/predicate/object."""
        payload = f"{self.subject}\x00{self.predicate}\x00{self.object_}"
        return ClaimID("claim:" + hashlib.sha256(payload.encode()).hexdigest()[:16])


@dataclass(frozen=True)
class Attestation:
    """A second node vouches for a claim."""

    claim_id: ClaimID
    attested_by: str
    attested_at: float = field(default_factory=time.time)
    signature: bytes = b""


@dataclass(frozen=True)
class Dispute:
    """A node disputes a claim."""

    claim_id: ClaimID
    disputed_by: str
    reason: str
    disputed_at: float = field(default_factory=time.time)
    counter_claim_id: ClaimID | None = None


class ClaimStore:
    """Append-only content-addressed claim store (in-memory prototype).

    Production implementation will use a Merkle-DAG store backed by SQLite.
    EBKH adapter (PostGIS + OSINT) plugs in via the `import_ebkh_record` method.
    """

    def __init__(self) -> None:
        self._claims: dict[ClaimID, Claim] = {}
        self._attestations: dict[ClaimID, list[Attestation]] = {}
        self._disputes: dict[ClaimID, list[Dispute]] = {}

    def add_claim(self, claim: Claim) -> ClaimID:
        cid = claim.content_id()
        if cid not in self._claims:
            self._claims[cid] = claim
        return cid

    def attest(self, attestation: Attestation) -> None:
        self._attestations.setdefault(attestation.claim_id, []).append(attestation)

    def dispute(self, dispute: Dispute) -> None:
        self._disputes.setdefault(dispute.claim_id, []).append(dispute)

    def get_claim(self, claim_id: ClaimID) -> Claim | None:
        return self._claims.get(claim_id)

    def find_by_subject(self, subject: str) -> list[Claim]:
        return [c for c in self._claims.values() if c.subject == subject]

    def attestation_count(self, claim_id: ClaimID) -> int:
        return len(self._attestations.get(claim_id, []))

    def is_disputed(self, claim_id: ClaimID) -> bool:
        return bool(self._disputes.get(claim_id))

    def import_ebkh_record(
        self, record: dict[str, Any], asserted_by: str, community_id: str
    ) -> ClaimID:
        """Import a record from Christof's EBKH system as a Claim.

        Expects record to have at minimum: subject, predicate, object, source_url.
        """
        source = ClaimSource(
            source_id=SourceID(record.get("ebkh_id", str(uuid.uuid4()))),
            source_type="ebkh",
            url=record.get("source_url"),
            reliability_score=float(record.get("reliability", 1.0)),
        )
        claim = Claim(
            claim_id=ClaimID(str(uuid.uuid4())),
            subject=str(record.get("subject", "")),
            predicate=str(record.get("predicate", "asserts")),
            object_=str(record.get("object", "")),
            asserted_by=asserted_by,
            sources=(source,),
            community_id=community_id,
        )
        return self.add_claim(claim)

    def summary(self) -> dict:
        return {
            "claims": len(self._claims),
            "attestations": sum(len(v) for v in self._attestations.values()),
            "disputes": sum(len(v) for v in self._disputes.values()),
        }
