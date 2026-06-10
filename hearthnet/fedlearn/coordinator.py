"""M28 — Federated Learning / LoRA aggregation (experimental, Phase 3).

FedAvg on LoRA adapter weight deltas. Each node trains locally;
only adapter deltas (not raw data or full weights) are shared.
Gated by config.research.federated_learning = True.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import NewType

RoundID = NewType("RoundID", str)


@dataclass(frozen=True)
class RoundManifest:
    """Describes a federated learning round."""
    round_id: RoundID
    base_model_id: str
    coordinator_node_id: str
    community_id: str
    lora_rank: int = 16
    lora_alpha: float = 32.0
    learning_rate: float = 2e-4
    min_participants: int = 2
    max_participants: int = 20
    round_timeout_seconds: int = 3600
    created_at: float = field(default_factory=time.time)
    coordinator_sig: bytes = b""


@dataclass
class ParticipantSubmission:
    round_id: RoundID
    participant_node_id: str
    delta_bytes: bytes          # serialised LoRA state dict subset (safetensors format)
    num_samples: int
    submitted_at: float = field(default_factory=time.time)
    participant_sig: bytes = b""


class FedLearnCoordinator:
    """Orchestrates a federated learning round.

    Experimental. Requires peft and torch.
    Only active when config.research.federated_learning = True.
    """

    def __init__(self, keypair=None, bus=None) -> None:
        self._keypair = keypair
        self._bus = bus
        self._rounds: dict[RoundID, RoundManifest] = {}
        self._submissions: dict[RoundID, list[ParticipantSubmission]] = {}

    def create_round(
        self,
        base_model_id: str,
        community_id: str,
        **kwargs,
    ) -> RoundManifest:
        """Create a new federated learning round manifest."""
        round_id = RoundID(str(uuid.uuid4()))
        manifest = RoundManifest(
            round_id=round_id,
            base_model_id=base_model_id,
            coordinator_node_id=getattr(self._keypair, "node_id_short", "unknown"),
            community_id=community_id,
            **kwargs,
        )
        self._rounds[round_id] = manifest
        self._submissions[round_id] = []
        return manifest

    def submit(self, submission: ParticipantSubmission) -> bool:
        """Accept a participant's LoRA delta submission."""
        if submission.round_id not in self._rounds:
            return False
        self._submissions[submission.round_id].append(submission)
        return True

    def aggregate(self, round_id: RoundID) -> bytes | None:
        """FedAvg: weighted average of submitted LoRA deltas.

        Returns aggregated delta bytes or None if not enough participants.
        Raises NotImplementedError — actual aggregation requires peft+torch.
        """
        subs = self._submissions.get(round_id, [])
        manifest = self._rounds.get(round_id)
        if manifest is None or len(subs) < manifest.min_participants:
            return None
        raise NotImplementedError(
            "FedLearnCoordinator.aggregate() requires peft and torch. "
            "This is an experimental Phase 3 feature (M28)."
        )

    def round_status(self, round_id: RoundID) -> dict:
        manifest = self._rounds.get(round_id)
        if manifest is None:
            return {"error": "not_found"}
        subs = self._submissions.get(round_id, [])
        return {
            "round_id": round_id,
            "base_model_id": manifest.base_model_id,
            "participants": len(subs),
            "min_required": manifest.min_participants,
            "ready_to_aggregate": len(subs) >= manifest.min_participants,
        }
