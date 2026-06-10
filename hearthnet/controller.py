from __future__ import annotations

from typing import Any

from hearthnet.node import HearthNode


class HearthNetController:
    def __init__(self, node: HearthNode) -> None:
        self.node = node

    def snapshot(self) -> dict[str, Any]:
        return self.node.snapshot()

    def apply_emergency_probe(self, results: dict[str, bool]) -> dict[str, Any]:
        self.node.detector.apply_probe_results(results)
        return self.snapshot()
