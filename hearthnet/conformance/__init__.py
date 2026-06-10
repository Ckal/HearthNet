"""X09 — Conformance Suite package.

Provides black-box tests that define "HearthNet-compliant" for any implementation.

Suites:
  identity   — M01 Ed25519 signing, canonical JSON, node manifest format
  bus        — M03 capability registration, routing, error codes
  transport  — X01 HTTP endpoints, response schemas, SSE stream format
  services   — M04-M13 Phase 1 capability contracts
  federation — M14 cross-community capability proxy (Phase 2)

Usage from Python:
  from hearthnet.conformance import ConformanceRunner
  runner = ConformanceRunner(bus=node.bus)
  report = await runner.run(suite="1.0")

Usage from CLI:
  python -m hearthnet.cli call protocol.conformance.report 1 0 '{"suite_version":"1.0"}'
"""

from __future__ import annotations

from hearthnet.conformance.runner import ConformanceRunner, ConformanceReport

__all__ = ["ConformanceRunner", "ConformanceReport"]
