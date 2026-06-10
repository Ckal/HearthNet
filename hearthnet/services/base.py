from __future__ import annotations

from typing import Any, Protocol


class Service(Protocol):
    name: str
    version: str

    def capabilities(self) -> list[tuple[Any, ...]]: ...
