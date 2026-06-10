from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from .types import Event, EventType

if TYPE_CHECKING:
    from .log import EventLog


class MaterialisedView(Protocol):
    """Protocol that all consuming-module views must satisfy."""

    def reset(self) -> None:
        """Clear all state (called before a full replay)."""
        ...

    def apply(self, event: Event) -> None:
        """Incorporate a single event into the view's state."""
        ...

    def snapshot_state(self) -> dict:
        """Return a JSON-serialisable representation of current state."""
        ...

    def restore_state(self, state: dict) -> None:
        """Reinstate state produced by snapshot_state()."""
        ...


class ReplayEngine:
    """Routes events to registered materialised views."""

    def __init__(self, log: EventLog) -> None:
        self.log = log
        # view_name -> (view, set of event_types it cares about or None for all)
        self._views: dict[str, tuple[MaterialisedView, frozenset[str] | None]] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        name: str,
        view: MaterialisedView,
        event_types: list[EventType] | None = None,
    ) -> None:
        """Register *view* under *name*. Pass ``event_types=None`` for all types."""
        ft: frozenset[str] | None = frozenset(event_types) if event_types else None
        self._views[name] = (view, ft)

    # Alias used in task spec
    def register_view(
        self,
        view: MaterialisedView,
        event_types: list[EventType],
    ) -> None:
        name = type(view).__name__
        self.register(name, view, event_types)

    # ------------------------------------------------------------------
    # Replay
    # ------------------------------------------------------------------

    def rebuild(self, view_name: str, from_lamport: int = 0) -> None:
        """Reset the named view and replay all relevant events from *from_lamport*."""
        view, ft = self._views[view_name]
        view.reset()
        event_types = list(ft) if ft is not None else None
        for event in self.log.replay(since_lamport=from_lamport, event_types=event_types):  # type: ignore[arg-type]
            view.apply(event)

    def rebuild_all(self, from_lamport: int = 0) -> None:
        """Reset and replay all registered views."""
        for name in list(self._views):
            self.rebuild(name, from_lamport)

    # Alias used in task spec
    def replay_all(self) -> None:
        self.rebuild_all(from_lamport=0)

    def replay_since(self, lamport: int) -> None:
        """Replay (without reset) all views for events at lamport >= *lamport*."""
        # Collect all event types across views
        for _name, (view, ft) in self._views.items():
            event_types = list(ft) if ft is not None else None
            for event in self.log.replay(since_lamport=lamport, event_types=event_types):  # type: ignore[arg-type]
                view.apply(event)

    # ------------------------------------------------------------------
    # Live fanout
    # ------------------------------------------------------------------

    def _on_event(self, event: Event) -> None:
        """Route a newly-arrived event to all subscribed views."""
        for _name, (view, ft) in self._views.items():
            if ft is None or event.event_type in ft:
                view.apply(event)

    # Alias used in spec
    on_event = _on_event
