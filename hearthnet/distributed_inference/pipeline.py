"""Pipeline orchestrator for distributed inference (M26 — experimental)."""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from hearthnet.distributed_inference.shard import ShardDescriptor


@dataclass
class Pipeline:
    """A planned pipeline: ordered list of shards covering layers 0..N."""
    pipeline_id: str
    model_id: str
    shards: list[ShardDescriptor]
    established_at: float = field(default_factory=time.time)
    status: str = "planned"   # "planned" | "active" | "failed" | "done"

    @property
    def is_complete(self) -> bool:
        """True if shards cover a contiguous range starting at 0."""
        if not self.shards:
            return False
        sorted_shards = sorted(self.shards, key=lambda s: s.layer_lo)
        if sorted_shards[0].layer_lo != 0:
            return False
        expected_next = 0
        for shard in sorted_shards:
            if shard.layer_lo != expected_next:
                return False
            expected_next = shard.layer_hi + 1
        return True


class PipelineOrchestrator:
    """Constructs and executes layer pipelines across multiple shard servers.

    Experimental Phase 3 feature. Not production-ready.
    The orchestrator:
    1. Finds available shards from the capability bus
    2. Plans a pipeline covering all layers
    3. Chains forward passes across shards
    4. Streams token output back to the caller
    """

    def __init__(self, bus=None) -> None:
        self._bus = bus
        self._pipelines: dict[str, Pipeline] = {}

    def plan(self, model_id: str, available_shards: list[ShardDescriptor]) -> Pipeline | None:
        """Choose a minimal set of shards that covers layers 0..N continuously."""
        import uuid
        model_shards = [s for s in available_shards if s.model_id == model_id]
        if not model_shards:
            return None

        # Greedy cover: sort by layer_lo, pick first shard that starts where we left off
        sorted_shards = sorted(model_shards, key=lambda s: s.layer_lo)
        chosen: list[ShardDescriptor] = []
        expected = 0
        for shard in sorted_shards:
            if shard.layer_lo == expected:
                chosen.append(shard)
                expected = shard.layer_hi + 1

        pipeline = Pipeline(
            pipeline_id=str(uuid.uuid4()),
            model_id=model_id,
            shards=chosen,
        )
        if pipeline.is_complete:
            self._pipelines[pipeline.pipeline_id] = pipeline
            return pipeline
        return None

    async def run(self, pipeline_id: str, prompt_tokens: list[int]) -> list[int]:
        """Execute a pipeline. Returns generated tokens.

        Experimental — raises NotImplementedError in current state.
        """
        raise NotImplementedError(
            "PipelineOrchestrator.run() is not yet implemented. "
            "This is an experimental Phase 3 feature (M26). "
            "Enable with config.research.distributed_inference = True."
        )

    def list_pipelines(self) -> list[dict]:
        return [
            {
                "pipeline_id": p.pipeline_id,
                "model_id": p.model_id,
                "shard_count": len(p.shards),
                "complete": p.is_complete,
                "status": p.status,
            }
            for p in self._pipelines.values()
        ]
