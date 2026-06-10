"""SSE writer/reader helpers."""
from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator


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
            except asyncio.TimeoutError:
                if self._done:
                    break
                yield ": keepalive\n\n"
            except Exception:
                if self._done:
                    break
                yield ": keepalive\n\n"
