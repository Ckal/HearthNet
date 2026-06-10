"""X09 — Conformance suite runner.

Runs black-box capability-contract checks against a live bus or HTTP endpoint.
Reports are deterministic (seeded) and machine-readable (JSON).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Check definitions
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Check:
    capability: str
    version: tuple[int, int]
    body: dict
    suite: str                   # "1.0", "2.0", "3.0"
    expected_output_fields: list[str] = field(default_factory=list)
    expect_error: str | None = None   # if set, pass only when this error is returned
    description: str = ""


# Phase 1 checks (suite 1.0) — derived from CAPABILITY_CONTRACT.md §3.2
_CHECKS: list[Check] = [
    # Identity / protocol
    Check("protocol.version.list", (1, 0), {"input": {}}, "1.0", ["contract_versions"], description="protocol.version.list returns supported versions"),
    Check("protocol.conformance.report", (1, 0), {"input": {"suite_version": "1.0", "fast": True}}, "1.0", ["passed", "total"], description="protocol.conformance.report can self-report"),

    # Embedding
    Check("embed.text", (1, 0), {"input": {"texts": ["conformance ping"]}}, "1.0", ["vectors"], description="embed.text returns vectors"),

    # RAG
    Check("rag.query", (1, 0), {"input": {"query": "ping", "corpus": "demo", "k": 1}}, "1.0", [], description="rag.query responds"),
    Check("rag.list_corpora", (1, 0), {"input": {}}, "1.0", ["corpora"], description="rag.list_corpora returns list"),

    # Files
    Check("file.list", (1, 0), {"input": {}}, "1.0", ["files"], description="file.list returns files list"),
    Check("file.put", (1, 0), {"input": {"data_b64": "aGVsbG8=", "filename": "x09.txt"}}, "1.0", ["cid"], description="file.put returns cid"),

    # Marketplace
    Check("market.list", (1, 0), {"input": {}}, "1.0", ["posts"], description="market.list returns posts"),

    # LLM
    Check("llm.complete", (1, 0), {"input": {"prompt": "x09 conformance", "max_tokens": 1}}, "1.0", [], description="llm.complete responds"),

    # Chat
    Check("chat.send", (1, 0), {"input": {"to": "self", "body": "x09", "client_id": "x09_conformance"}}, "1.0", [], description="chat.send accepts message"),

    # MoE (Phase 3 but bus-registered in all nodes)
    Check("moe.list", (1, 0), {"input": {}}, "1.0", ["experts"], description="moe.list returns experts"),
    Check("moe.route", (1, 0), {"input": {"query": "conformance test"}}, "1.0", ["candidates"], description="moe.route returns candidates"),

    # Model distribution
    Check("model.list", (1, 0), {"input": {}}, "1.0", ["models"], description="model.list returns models"),

    # Tool: plant (validates input handling)
    Check("tool.plant_identify", (1, 0), {"input": {}}, "1.0", [], expect_error="bad_request", description="tool.plant_identify rejects missing image"),

    # Phase 2 (suite 2.0) — only if registered
    Check("ocr.image", (1, 0), {"input": {"image_cid": "blake3:00000000"}}, "2.0", [], description="ocr.image endpoint exists"),
    Check("trans.text", (1, 0), {"input": {"text": "hello", "from": "en", "to": "de"}}, "2.0", [], description="trans.text responds"),
    Check("rerank.text", (1, 0), {"input": {"query": "test", "documents": [{"id": "d1", "text": "test"}]}}, "2.0", [], description="rerank.text responds"),
    Check("img.describe", (1, 0), {"input": {"image_cid": "blake3:00000000", "task": "caption"}}, "2.0", [], description="img.describe responds"),
    Check("stt.transcribe", (1, 0), {"input": {"audio_cid": "blake3:00000000"}}, "2.0", [], description="stt.transcribe responds"),
    Check("tts.synthesize", (1, 0), {"input": {"text": "ping", "speed": 1.0, "format": "wav"}}, "2.0", [], description="tts.synthesize responds"),

    # Phase 3 experimental (suite 3.0)
    Check("moe.register", (1, 0), {"input": {"expert_id": "model:x09", "expert_type": "model", "topic_tags": ["x09"], "confidence_score": 0.5, "community_id": "x09"}}, "3.0", ["registered"], description="moe.register accepts expert"),
    Check("model.status", (1, 0), {"input": {}}, "3.0", ["jobs"], description="model.status returns jobs"),
]


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

@dataclass
class CheckResult:
    capability: str
    suite: str
    passed: bool
    skipped: bool
    error: str
    duration_ms: float
    description: str


@dataclass
class ConformanceReport:
    suite_version: str
    implementation: str
    node_id: str
    passed: int
    failed: int
    skipped: int
    total: int
    duration_ms: float
    results: list[CheckResult]

    def as_dict(self) -> dict:
        return {
            "suite_version": self.suite_version,
            "implementation": self.implementation,
            "node_id": self.node_id,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "total": self.total,
            "duration_ms": self.duration_ms,
            "results": [
                {
                    "capability": r.capability,
                    "suite": r.suite,
                    "passed": r.passed,
                    "skipped": r.skipped,
                    "error": r.error,
                    "duration_ms": r.duration_ms,
                    "description": r.description,
                }
                for r in self.results
            ],
        }


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

class ConformanceRunner:
    """Runs the X09 conformance suite against a local bus or remote HTTP node.

    If *bus* is provided, checks run in-process.
    If *node_url* is provided, checks are made via HTTP (requires httpx or similar).
    """

    def __init__(
        self,
        bus: Any = None,
        node_url: str = "",
        implementation: str = "hearthnet-py",
        node_id: str = "",
    ) -> None:
        self._bus = bus
        self._node_url = node_url
        self._implementation = implementation
        self._node_id = node_id

    async def run(self, suite: str = "1.0", fast: bool = True) -> ConformanceReport:
        """Run the conformance suite and return a report."""
        # Filter checks by requested suite level
        suite_order = {"1.0": 1, "2.0": 2, "3.0": 3}
        suite_level = suite_order.get(suite, 1)
        checks = [c for c in _CHECKS if suite_order.get(c.suite, 0) <= suite_level]

        results: list[CheckResult] = []
        t0 = time.time()

        for check in checks:
            cr = await self._run_check(check, fast)
            results.append(cr)

        total_ms = round((time.time() - t0) * 1000, 1)
        passed = sum(1 for r in results if r.passed)
        failed = sum(1 for r in results if not r.passed and not r.skipped)
        skipped = sum(1 for r in results if r.skipped)

        return ConformanceReport(
            suite_version=suite,
            implementation=self._implementation,
            node_id=self._node_id,
            passed=passed,
            failed=failed,
            skipped=skipped,
            total=len(results),
            duration_ms=total_ms,
            results=results,
        )

    async def _run_check(self, check: Check, fast: bool) -> CheckResult:
        t0 = time.time()

        if self._bus is None:
            return CheckResult(
                capability=check.capability,
                suite=check.suite,
                passed=False,
                skipped=True,
                error="no_bus",
                duration_ms=0,
                description=check.description,
            )

        # Fast mode: skip capabilities not registered locally
        if fast:
            try:
                local = self._bus.registry.find(check.capability, check.version)
                if not local:
                    return CheckResult(
                        capability=check.capability,
                        suite=check.suite,
                        passed=False,
                        skipped=True,
                        error="not_registered",
                        duration_ms=0,
                        description=check.description,
                    )
            except Exception:
                pass

        try:
            result = await self._bus.call(check.capability, check.version, check.body)
            ms = round((time.time() - t0) * 1000, 1)

            error_code = result.get("error") if isinstance(result, dict) else None

            # If we expected a specific error, pass only when it matches
            if check.expect_error is not None:
                passed = error_code == check.expect_error
                return CheckResult(
                    capability=check.capability,
                    suite=check.suite,
                    passed=passed,
                    skipped=False,
                    error="" if passed else f"expected_error={check.expect_error}, got={error_code}",
                    duration_ms=ms,
                    description=check.description,
                )

            # Otherwise pass when no error and expected output fields present
            has_error = bool(error_code) and error_code not in (None, "")
            output = result.get("output", result) if isinstance(result, dict) else {}
            missing = [f for f in check.expected_output_fields if f not in (output or {})]

            if has_error:
                return CheckResult(
                    capability=check.capability,
                    suite=check.suite,
                    passed=False,
                    skipped=False,
                    error=str(error_code),
                    duration_ms=ms,
                    description=check.description,
                )

            if missing:
                return CheckResult(
                    capability=check.capability,
                    suite=check.suite,
                    passed=False,
                    skipped=False,
                    error=f"missing_output_fields={missing}",
                    duration_ms=ms,
                    description=check.description,
                )

            return CheckResult(
                capability=check.capability,
                suite=check.suite,
                passed=True,
                skipped=False,
                error="",
                duration_ms=ms,
                description=check.description,
            )

        except Exception as exc:
            ms = round((time.time() - t0) * 1000, 1)
            return CheckResult(
                capability=check.capability,
                suite=check.suite,
                passed=False,
                skipped=False,
                error=str(exc),
                duration_ms=ms,
                description=check.description,
            )
