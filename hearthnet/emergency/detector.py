from __future__ import annotations

from hearthnet.bus import CapabilityBus
from hearthnet.discovery import PeerRegistry
from hearthnet.emergency.state import EmergencyState, StateBus


class Detector:
    def __init__(self, bus: CapabilityBus, state_bus: StateBus, peers: PeerRegistry) -> None:
        self.bus = bus
        self.state_bus = state_bus
        self.peers = peers

    def apply_probe_results(self, probe_results: dict[str, bool]) -> EmergencyState:
        previous = self.state_bus.current().mode
        state = self.state_bus.emit_probe(probe_results)
        if previous != "offline" and state.mode == "offline":
            self.bus.deregister_internet_capabilities()
            self.peers.set_pruning_aggressive(True)
        elif previous == "offline" and state.mode == "online":
            self.bus.restore_internet_capabilities()
            self.peers.set_pruning_aggressive(False)
        return state
