"""Shard descriptors and server for distributed inference (M26 — experimental)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

ShardID = str


@dataclass(frozen=True)
class ShardDescriptor:
    """Describes one contiguous layer range hosted by a node."""

    shard_id: ShardID  # "<model_id>:<lo>-<hi>"
    model_id: str
    layer_lo: int
    layer_hi: int  # inclusive
    node_id: str
    endpoint: str
    dtype: str = "float16"  # "float16" | "bfloat16" | "int8"
    advertised_at: float = field(default_factory=time.time)

    @property
    def layer_count(self) -> int:
        return self.layer_hi - self.layer_lo + 1


class ShardServer:
    """Hosts one contiguous shard.

    Loaded lazily on first use; evictable under memory pressure.
    This is an experimental module — only active when
    config.research.distributed_inference = True.
    """

    def __init__(self, descriptor: ShardDescriptor) -> None:
        self._desc = descriptor
        self._model: Any = None
        self._loaded = False

    @property
    def descriptor(self) -> ShardDescriptor:
        return self._desc

    def is_loaded(self) -> bool:
        return self._loaded

    def load(self) -> None:
        """Load the shard weights.  Raises ImportError if torch unavailable."""
        try:
            import torch  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "PyTorch is required for distributed inference. Install: pip install torch"
            ) from exc
        # Actual weight loading would go here; placeholder for the research prototype.
        self._loaded = True

    def evict(self) -> None:
        """Free shard memory."""
        self._model = None
        self._loaded = False

    async def forward(self, hidden_states: bytes, dtype: str = "float16") -> bytes:
        """Run one forward pass through this shard.

        hidden_states: raw tensor bytes (X08 tensor-transport format)
        Returns: raw output tensor bytes
        """
        if not self._loaded:
            self.load()
        # Placeholder — real implementation uses torch to slice model and forward.
        raise NotImplementedError(
            "ShardServer.forward() is not yet implemented for this shard. "
            "This is an experimental Phase 3 feature."
        )

    def health(self) -> dict:
        return {
            "shard_id": self._desc.shard_id,
            "loaded": self._loaded,
            "layers": f"{self._desc.layer_lo}-{self._desc.layer_hi}",
            "status": "loaded" if self._loaded else "unloaded",
        }
