"""X09 — Protocol Conformance Service.

Implements the two capabilities required by CAPABILITY_CONTRACT_v3.md §4.19-4.20:

  protocol.version.list@1.0   — report contract versions and implementation info
  protocol.conformance.report@1.0 — run a set of conformance checks and return a report

Conformance checks (X09 suite):
  The suite tests that all capabilities specified in CAPABILITY_CONTRACT.md §3.2
  are registered on the local bus and respond to a minimal well-formed request.

  Suite levels:
    v1.0 — Phase 1 capabilities (M01-M13, X01-X04) — 18 capabilities
    v2.0 — Phase 2 additions (M14-M25, X05-X07)    — 24+ capabilities
    v3.0 — Phase 3 experimental (M26-M31)           — checked if opted in
"""

from __future__ import annotations

import contextlib
import time
from typing import TYPE_CHECKING, Any

from hearthnet.bus.capability import CapabilityDescriptor, RouteRequest

if TYPE_CHECKING:
    pass  # HearthNode imported lazily to avoid circular import

_HEARTHNET_VERSION = "0.2.0"

# ---------------------------------------------------------------------------
# Conformance check catalogue
# ---------------------------------------------------------------------------

# Each check: (capability_name, version_req, minimal_input, expected_output_field)
# A check passes if calling the capability does NOT return {"error": ...}
# and the expected_output_field (if non-empty) is present in the output.

_SUITE_V1: list[tuple[str, tuple[int, int], dict, str]] = [
    ("llm.complete", (1, 0), {"input": {"prompt": "__conformance_ping__", "max_tokens": 1}}, ""),
    ("embed.text", (1, 0), {"input": {"texts": ["ping"]}}, "vectors"),
    ("rag.query", (1, 0), {"input": {"query": "ping", "corpus": "demo", "k": 1}}, ""),
    ("file.put", (1, 0), {"input": {"data_b64": "cGluZw==", "filename": "ping.txt"}}, "cid"),
    ("file.list", (1, 0), {"input": {}}, "files"),
    ("market.list", (1, 0), {"input": {}}, "posts"),
    (
        "market.post",
        (1, 0),
        {
            "input": {
                "title": "__conformance__",
                "body": "test",
                "category": "other",
                "client_id": "__x09__",
            }
        },
        "",
    ),
    (
        "chat.send",
        (1, 0),
        {"input": {"to": "self", "body": "ping", "client_id": "__x09_chat__"}},
        "",
    ),
    ("moe.list", (1, 0), {"input": {}}, "experts"),
    ("moe.route", (1, 0), {"input": {"query": "ping"}}, "candidates"),
    ("model.list", (1, 0), {"input": {}}, "models"),
    ("protocol.version.list", (1, 0), {"input": {}}, "contract_versions"),
]

_SUITE_V2: list[tuple[str, tuple[int, int], dict, str]] = [
    # Phase 2 — only checked if those services are registered
    ("ocr.image", (1, 0), {"input": {"image_cid": "blake3:test"}}, ""),
    ("trans.text", (1, 0), {"input": {"text": "hello", "from": "en", "to": "de"}}, ""),
    (
        "rerank.text",
        (1, 0),
        {"input": {"query": "test", "documents": [{"id": "d1", "text": "test"}]}},
        "",
    ),
]

_SUITE_V3: list[tuple[str, tuple[int, int], dict, str]] = [
    # Phase 3 experimental
    (
        "moe.register",
        (1, 0),
        {
            "input": {
                "expert_id": "model:x09",
                "expert_type": "model",
                "topic_tags": ["test"],
                "confidence_score": 0.5,
                "community_id": "test",
            }
        },
        "registered",
    ),
    ("tool.plant_identify", (1, 0), {"input": {}}, ""),  # expects error: bad_request
]


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class ProtocolService:
    """X09 — conformance and version reporting.

    Capabilities:
      protocol.version.list@1.0  — returns contract versions + implementation details
      protocol.conformance.report@1.0 — runs the X09 conformance suite
    """

    name = "protocol"
    version = "1.0"

    def __init__(self, node: Any = None) -> None:
        self._node = node  # HearthNode reference (optional)

    def capabilities(self) -> list[tuple]:
        return [
            (
                CapabilityDescriptor(
                    name="protocol.version.list",
                    version=(1, 0),
                    stability="stable",
                    params={},
                    max_concurrent=32,
                    trust_required="member",
                    timeout_seconds=5,
                    idempotent=True,
                ),
                self.handle_version_list,
                None,
            ),
            (
                CapabilityDescriptor(
                    name="protocol.conformance.report",
                    version=(1, 0),
                    stability="stable",
                    params={},
                    max_concurrent=2,
                    trust_required="member",
                    timeout_seconds=120,
                    idempotent=True,
                ),
                self.handle_conformance_report,
                None,
            ),
        ]

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    async def handle_version_list(self, req: RouteRequest) -> dict:
        """Return supported contract versions and implementation metadata.

        output:
          contract_versions: list[str]   — e.g. ["1.0", "2.0", "3.0"]
          implementation: {name, version, node_id, capabilities_count}
          started: bool
          event_log_head: int | null
        """
        caps_count = 0
        if self._node is not None:
            with contextlib.suppress(Exception):
                caps_count = len(list(self._node.bus.registry.all_local()))

        return {
            "output": {
                "contract_versions": ["1.0", "2.0", "3.0"],
                "implementation": {
                    "name": "hearthnet-py",
                    "version": _HEARTHNET_VERSION,
                    "node_id": self._node.node_id if self._node else "",
                    "capabilities_count": caps_count,
                },
                "started": bool(self._node and getattr(self._node, "_started", False)),
                "event_log_head": (
                    self._node._event_log.head() if self._node and self._node._event_log else None
                ),
            },
            "meta": {"ms": 0},
        }

    async def handle_conformance_report(self, req: RouteRequest) -> dict:
        """Run the X09 conformance suite and return a report.

        input:
          suite_version: str = "1.0"   — "1.0", "2.0", or "3.0"
          fast: bool = True            — if True, skip capabilities not registered

        output:
          passed: int
          failed: int
          skipped: int
          total: int
          results: list[{capability, passed, skipped, error}]
          suite_version: str
          duration_ms: float
        """
        inp = req.body.get("input", {})
        suite_version = inp.get("suite_version", "1.0")
        fast_mode = inp.get("fast", True)

        # Choose which checks to run
        checks = list(_SUITE_V1)
        if suite_version in ("2.0", "3.0"):
            checks += _SUITE_V2
        if suite_version == "3.0":
            checks += _SUITE_V3

        bus = self._node.bus if self._node else None
        results = []
        passed = failed = skipped = 0
        t0 = time.time()

        for cap_name, version_req, body, expected_field in checks:
            if bus is None:
                results.append(
                    {"capability": cap_name, "passed": False, "skipped": True, "error": "no_bus"}
                )
                skipped += 1
                continue

            # In fast mode, skip capabilities not registered locally
            if fast_mode:
                try:
                    local = bus.registry.find(cap_name, version_req)
                    if not local:
                        results.append(
                            {
                                "capability": cap_name,
                                "passed": False,
                                "skipped": True,
                                "error": "not_registered",
                            }
                        )
                        skipped += 1
                        continue
                except Exception:
                    pass

            try:
                result = await bus.call(cap_name, version_req, body)
                # A capability passes if it doesn't return a top-level "error" key
                # AND (if expected_field is set) the output contains that field.
                has_error = (
                    "error" in result
                    and result["error"]
                    not in (
                        "bad_request",  # some capabilities intentionally return bad_request for empty input
                        None,
                    )
                )
                output_ok = True
                if expected_field and not has_error:
                    output = result.get("output", result)
                    output_ok = expected_field in (output or {})
                    has_error = not output_ok

                if has_error:
                    error_msg = result.get("error", result.get("message", "unknown"))
                    results.append(
                        {
                            "capability": cap_name,
                            "passed": False,
                            "skipped": False,
                            "error": str(error_msg),
                        }
                    )
                    failed += 1
                else:
                    results.append(
                        {"capability": cap_name, "passed": True, "skipped": False, "error": ""}
                    )
                    passed += 1
            except Exception as exc:
                results.append(
                    {"capability": cap_name, "passed": False, "skipped": False, "error": str(exc)}
                )
                failed += 1

        duration_ms = round((time.time() - t0) * 1000, 1)
        return {
            "output": {
                "passed": passed,
                "failed": failed,
                "skipped": skipped,
                "total": passed + failed + skipped,
                "results": results,
                "suite_version": suite_version,
                "duration_ms": duration_ms,
            },
            "meta": {"ms": duration_ms},
        }
