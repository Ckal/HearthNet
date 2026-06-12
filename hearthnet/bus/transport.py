"""Modular, conformant bus transport — pluggable delivery strategies.

The bus calls ``transport.call(node_id, req)`` whenever a capability resolves to a
*remote* provider. Different network situations need different ways to reach that
peer:

* **in-process** — the peer's bus lives in the same Python process (tests, the
  in-process multi-node demo).
* **direct HTTP** — the peer has a reachable ``/bus/v1/call`` endpoint (e.g. the
  public HF Space, or a LAN node).
* **relay** — the peer is behind NAT and can only be reached by enqueuing into a
  mailbox on a shared relay hub that it polls (see
  :mod:`hearthnet.transport.relay_hub` / :mod:`hearthnet.transport.relay_client`).

:class:`CompositeTransport` keeps the in-process and direct-HTTP fast paths built
in (inherited from :class:`~hearthnet.bus.http_transport.HttpBusTransport`) and
adds an ordered list of pluggable :class:`DeliveryStrategy` objects that are
consulted when those fast paths cannot reach the node. New transports (WebRTC,
tunnels, …) are added by registering another strategy — the bus never changes.

This is the "system of conformance" the mesh extends: any object implementing the
:class:`DeliveryStrategy` protocol can participate.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from hearthnet.bus import BusError, InMemoryTransport
from hearthnet.bus.capability import RouteRequest
from hearthnet.bus.http_transport import HttpBusTransport


class _NotHandled:
    """Sentinel returned by a strategy that cannot reach the target node."""

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return "NOT_HANDLED"


#: Returned by :meth:`DeliveryStrategy.try_deliver` when the strategy declines.
NOT_HANDLED = _NotHandled()


@runtime_checkable
class DeliveryStrategy(Protocol):
    """A pluggable way to deliver a bus call to a remote node.

    Implementations return the peer's response dict on success, or
    :data:`NOT_HANDLED` if they cannot reach ``node_id`` (so the next strategy is
    tried). They may raise :class:`~hearthnet.bus.BusError` to signal a hard
    failure that should not fall through to other strategies.
    """

    name: str

    async def try_deliver(self, node_id: str, req: RouteRequest) -> Any:
        ...


class CompositeTransport(HttpBusTransport):
    """Transport that tries in-process → direct HTTP → registered strategies.

    Behaviour with no extra strategies is identical to
    :class:`~hearthnet.bus.http_transport.HttpBusTransport`, so it is a safe
    drop-in default. Call :meth:`add_strategy` (e.g. with a relay strategy) to
    extend reachability to NAT-bound peers without touching the bus.
    """

    def __init__(self) -> None:
        super().__init__()
        self._strategies: list[DeliveryStrategy] = []

    def add_strategy(self, strategy: DeliveryStrategy, *, front: bool = False) -> None:
        """Register an extra :class:`DeliveryStrategy`.

        Strategies are consulted in registration order after the built-in
        in-process and direct-HTTP paths. Pass ``front=True`` to prioritise it.
        """
        if front:
            self._strategies.insert(0, strategy)
        else:
            self._strategies.append(strategy)

    def remove_strategy(self, name: str) -> None:
        self._strategies = [s for s in self._strategies if getattr(s, "name", "") != name]

    def strategies(self) -> list[DeliveryStrategy]:
        return list(self._strategies)

    async def call(self, node_id: str, req: RouteRequest) -> dict[str, Any]:
        # 1) In-process target (shared transport / tests).
        if node_id in self._buses:
            return await InMemoryTransport.call(self, node_id, req)

        # 2) Direct HTTP target (peer advertises a reachable http/https endpoint).
        endpoint = self._resolve_endpoint(node_id)
        if endpoint is not None and endpoint.transport in ("http", "https"):
            return await self._http_call(endpoint, req)

        # 3) Pluggable strategies (relay, future WebRTC/tunnel, …).
        for strategy in self._strategies:
            result = await strategy.try_deliver(node_id, req)
            if result is not NOT_HANDLED:
                return result

        raise BusError("partition", f"node {node_id} is not reachable")
