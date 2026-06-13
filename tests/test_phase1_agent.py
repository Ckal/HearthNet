"""Phase 1 agent loop — M21 tool calls wired to the real capability bus.

No mocks: the bus, registry, router and demo ``rag.query`` capability are all
real in-process components. The only scripted piece is the LLM *role* itself
(``call_llm``), which is legitimate — a deterministic local stand-in for the
model's text output, exactly what a tiny local model would emit.
"""

from __future__ import annotations

import asyncio

from hearthnet.node import InMemoryNetwork
from hearthnet.services.llm.tools import ToolCall, ToolExecutor, default_tool_set


def _caller_with_demo():
    network = InMemoryNetwork()
    caller = network.add_node("ed25519:caller", "caller")
    provider = network.add_node("ed25519:provider", "provider")
    provider.install_demo_services()
    network.mesh_discover()
    return caller


def test_execute_dispatches_tool_to_real_bus() -> None:
    caller = _caller_with_demo()
    executor = default_tool_set(caller.bus)

    result = asyncio.run(
        executor.execute(
            ToolCall(id="t1", name="search_corpus", arguments={"query": "clean water"})
        )
    )

    assert result.is_error is False
    chunks = result.content["chunks"]
    assert chunks[0]["metadata"]["doc_title"] == "Water"


def test_react_loop_grounds_answer_in_tool_result() -> None:
    caller = _caller_with_demo()
    executor = default_tool_set(caller.bus)

    async def call_llm(messages: list[dict]) -> str:
        # Once the bus has handed back an Observation, answer; otherwise call a tool.
        if any("Observation from" in str(m.get("content", "")) for m in messages):
            return "Based on the corpus, the mesh has a Water document about clean water."
        return 'action: {"tool": "search_corpus", "query": "clean water"}'

    out = asyncio.run(executor.run_react_loop("Tell me about clean water", call_llm))

    assert "Water" in out["final"]
    tool_steps = [s for s in out["steps"] if s["type"] == "tool"]
    assert tool_steps and tool_steps[0]["name"] == "search_corpus"
    assert tool_steps[0]["is_error"] is False
    assert out["steps"][-1]["type"] == "final"


def test_react_loop_finalises_when_budget_exhausted() -> None:
    caller = _caller_with_demo()
    executor = default_tool_set(caller.bus)

    async def call_llm(messages: list[dict]) -> str:
        # Never stops calling tools on its own — force the budget guard to engage.
        if any("budget reached" in str(m.get("content", "")) for m in messages):
            return "Final answer after the tool budget was reached."
        return 'action: {"tool": "list_marketplace"}'

    out = asyncio.run(
        executor.run_react_loop("keep going", call_llm, max_iterations=2)
    )

    assert out["final"].startswith("Final answer")
    tool_steps = [s for s in out["steps"] if s["type"] == "tool"]
    assert len(tool_steps) == 2


def test_react_loop_recovers_from_bad_action_json() -> None:
    caller = _caller_with_demo()
    executor = default_tool_set(caller.bus)
    calls = {"n": 0}

    async def call_llm(messages: list[dict]) -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            return 'action: {not valid json}'
        return "Recovered and answering directly."

    out = asyncio.run(executor.run_react_loop("hi", call_llm))

    assert out["final"] == "Recovered and answering directly."
    assert calls["n"] == 2


def test_unbound_tool_errors_without_silent_fallback() -> None:
    # A tool whose capability is not on the bus must error clearly, not fabricate.
    caller = _caller_with_demo()
    executor = ToolExecutor(bus=caller.bus, tools=default_tool_set(caller.bus).definitions())

    result = asyncio.run(
        executor.execute(ToolCall(id="x", name="translate", arguments={"text": "hi", "target_lang": "de"}))
    )

    assert result.is_error is True
    assert "error" in result.content
