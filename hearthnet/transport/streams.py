"""SSE writer/reader helpers."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator


def encode_sse_frame(data: dict, event: str | None = None) -> str:
    """Encode a dict as an SSE frame string."""
    lines = []
    if event:
        lines.append(f"event: {event}")
    lines.append(f"data: {json.dumps(data, separators=(',', ':'))}")
    lines.append("")
    lines.append("")
    return "\n".join(lines)


async def parse_sse_stream(lines: AsyncIterator[str]) -> AsyncIterator[dict]:
    """Parse SSE stream lines into dicts."""
    async for line in lines:
        if line.startswith("data: "):
            try:
                yield json.loads(line[6:])
            except json.JSONDecodeError:
                pass


# ---------------------------------------------------------------------------
# Frame — typed SSE frame (X01 §3.2)
# ---------------------------------------------------------------------------


class Frame:
    """A single SSE frame with optional event tag and raw data.

    Spec: X01-transport §3.2 — wire format is ``data: <json>\\n\\n``
    with optional ``event: <tag>\\n`` prefix.
    """

    __slots__ = ("event", "data", "raw")

    def __init__(self, data: dict, event: str | None = None) -> None:
        self.data = data
        self.event = event
        self.raw = encode_sse_frame(data, event)

    def __repr__(self) -> str:
        return f"Frame(event={self.event!r}, data={self.data!r})"


# ---------------------------------------------------------------------------
# SseReader — parse an HTTP SSE response stream (X01 §3.2)
# ---------------------------------------------------------------------------


class SseReader:
    """Parse a streaming HTTP response into Frame objects.

    Typical usage with httpx::

        async with httpx.AsyncClient() as client:
            async with client.stream("POST", url, ...) as resp:
                reader = SseReader(resp.aiter_lines())
                async for frame in reader:
                    handle(frame)
    """

    def __init__(self, lines: AsyncIterator[str]) -> None:
        self._lines = lines

    async def __aiter__(self) -> AsyncIterator[Frame]:
        event_tag: str | None = None
        async for line in self._lines:
            if line.startswith("event:"):
                event_tag = line[6:].strip()
            elif line.startswith("data:"):
                raw = line[5:].strip()
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    data = {"raw": raw}
                yield Frame(data, event_tag)
                event_tag = None
            elif not line.strip():
                event_tag = None  # blank separator


class SseWriter:
    """Async generator that yields SSE-formatted strings."""

    def __init__(self):
        self._queue: asyncio.Queue | None = None
        self._done = False

    async def start(self) -> None:
        self._queue = asyncio.Queue()

    async def send(self, data: dict, event: str | None = None) -> None:
        if self._queue is not None:
            await self._queue.put(encode_sse_frame(data, event))

    def close(self) -> None:
        self._done = True

    async def __aiter__(self):
        while not self._done:
            try:
                frame = await asyncio.wait_for(self._queue.get(), timeout=0.5)
                yield frame
            except TimeoutError:
                if self._done:
                    break
                yield ": keepalive\n\n"
            except Exception:
                if self._done:
                    break
                yield ": keepalive\n\n"
