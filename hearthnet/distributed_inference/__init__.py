"""M26 — Distributed Inference (experimental, Phase 3).

Gated by config.research.distributed_inference = True.
Layer-shards an LLM across multiple LAN nodes (Petals-style).
"""

from __future__ import annotations

from hearthnet.distributed_inference.pipeline import Pipeline, PipelineOrchestrator
from hearthnet.distributed_inference.shard import ShardDescriptor, ShardServer

__all__ = ["Pipeline", "PipelineOrchestrator", "ShardDescriptor", "ShardServer"]
