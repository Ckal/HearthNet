from __future__ import annotations

import asyncio
import socket
from typing import Any

from hearthnet.constants import (
    EMERGENCY_PROBE_INTERVAL_OFFLINE_SECONDS,
    EMERGENCY_PROBE_INTERVAL_ONLINE_SECONDS,
    EMERGENCY_PROBE_TIMEOUT_SECONDS,
)
from hearthnet.emergency.state import EmergencyState, StateBus


class Detector:
    """Internet connectivity detector with async probe loop."""

    def __init__(
        self,
        bus: Any = None,
        state_bus: StateBus | None = None,
        peers: Any = None,
        probe_targets: list[str] | None = None,
    ) -> None:
        self._bus = bus
        self._state_bus = state_bus or StateBus()
        self._peers = peers
        self._probe_targets = probe_targets or [
            "1.1.1.1",
            "8.8.8.8",
            "https://cloudflare.com",
            "https://quad9.net",
        ]
        self._running = False
        self._task: asyncio.Task | None = None

    @property
    def state_bus(self) -> StateBus:
        return self._state_bus

    async def start(self) -> None:
        """Start the background probe loop."""
        self._running = True
        self._task = asyncio.create_task(self._probe_loop(), name="emergency-detector")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _probe_loop(self) -> None:
        while self._running:
            results = await self._probe_all()
            previous = self._state_bus.current().mode
            state = self._state_bus.emit_probe(results)

            if previous != "offline" and state.mode == "offline":
                await self._on_offline()
            elif previous == "offline" and state.mode in ("online", "degraded"):
                await self._on_restore()

            interval = (
                EMERGENCY_PROBE_INTERVAL_OFFLINE_SECONDS
                if state.mode == "offline"
                else EMERGENCY_PROBE_INTERVAL_ONLINE_SECONDS
            )
            await asyncio.sleep(interval)

    async def _probe_all(self) -> dict[str, bool]:
        tasks = {
            target: asyncio.create_task(self._probe_one(target))
            for target in self._probe_targets
        }
        results: dict[str, bool] = {}
        for target, task in tasks.items():
            try:
                results[target] = await asyncio.wait_for(task, timeout=EMERGENCY_PROBE_TIMEOUT_SECONDS)
            except (asyncio.TimeoutError, Exception):
                results[target] = False
        return results

    async def _probe_one(self, target: str) -> bool:
        """Probe a single target. DNS targets: resolve host. HTTP targets: HEAD request."""
        try:
            if target.startswith("http"):
                return await self._probe_http(target)
            return await self._probe_dns(target)
        except Exception:
            return False

    async def _probe_http(self, url: str) -> bool:
        try:
            import httpx

            async with httpx.AsyncClient(
                timeout=EMERGENCY_PROBE_TIMEOUT_SECONDS  # verify=True (default) — certificate
                # validation is intentional: we want to know if TLS infra is working too.
            ) as client:
                resp = await client.head(url)
                return resp.status_code < 500
        except ImportError:
            import urllib.request

            try:
                urllib.request.urlopen(url, timeout=EMERGENCY_PROBE_TIMEOUT_SECONDS)
                return True
            except Exception:
                return False
        except Exception:
            return False

    async def _probe_dns(self, host: str) -> bool:
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, socket.getaddrinfo, host, 53)
            return True
        except Exception:
            return False

    async def _on_offline(self) -> None:
        """Deregister internet-dependent capabilities, increase peer pruning aggressiveness."""
        if self._bus is not None:
            try:
                self._bus.deregister_internet_capabilities()
            except Exception:
                pass
        if self._peers is not None:
            try:
                self._peers.set_pruning_aggressive(True)
            except Exception:
                pass

    async def _on_restore(self) -> None:
        """Restore internet-dependent capabilities."""
        if self._bus is not None:
            try:
                self._bus.restore_internet_capabilities()
            except Exception:
                pass
        if self._peers is not None:
            try:
                self._peers.set_pruning_aggressive(False)
            except Exception:
                pass

    def apply_probe_results(self, probe_results: dict[str, bool]) -> EmergencyState:
        """Synchronous interface for manual/test use."""
        previous = self._state_bus.current().mode
        state = self._state_bus.emit_probe(probe_results)
        if previous != "offline" and state.mode == "offline":
            if self._bus is not None:
                self._bus.deregister_internet_capabilities()
            if self._peers is not None:
                self._peers.set_pruning_aggressive(True)
        elif previous == "offline" and state.mode in ("online", "degraded"):
            if self._bus is not None:
                self._bus.restore_internet_capabilities()
            if self._peers is not None:
                self._peers.set_pruning_aggressive(False)
        return state
