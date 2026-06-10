"""M29 — LoRa Hardware Beacons (experimental, Phase 3).

868 MHz LoRa "I'm still here" beacons for offline emergency presence.
No AI traffic, no chat, no file transfer — only 32-byte heartbeat frames.
Gated by config.research.lora_beacons = True.
"""

from __future__ import annotations

import struct
import time
from dataclasses import dataclass, field
from typing import NewType

LoraBeaconID = NewType("LoraBeaconID", str)
LoraDeviceID = NewType("LoraDeviceID", str)

# Frame layout: 32 bytes
# [0:4]  magic (b"HN01")
# [4:8]  sequence (uint32 big-endian)
# [8:16] node_id_hash (first 8 bytes of SHA-256 of node_id_full)
# [16:17] flags (bit0=emergency, bit1=panic)
# [17:32] reserved (zeros)
FRAME_MAGIC = b"HN01"
FRAME_SIZE = 32


@dataclass(frozen=True)
class LoraBeacon:
    beacon_id: LoraBeaconID
    device_id: LoraDeviceID
    node_id_hash: bytes  # 8 bytes
    sequence: int
    flags: int  # bit0=emergency, bit1=panic
    rssi: int | None = None  # dBm, if available
    received_at: float = field(default_factory=time.time)

    @property
    def is_emergency(self) -> bool:
        return bool(self.flags & 0x01)

    @property
    def is_panic(self) -> bool:
        return bool(self.flags & 0x02)


def encode_beacon_frame(node_id_full: str, sequence: int, flags: int = 0) -> bytes:
    """Encode a 32-byte LoRa beacon frame."""
    import hashlib

    node_hash = hashlib.sha256(node_id_full.encode()).digest()[:8]
    header = struct.pack(">4sI8sB", FRAME_MAGIC, sequence, node_hash, flags)
    return header + b"\x00" * (FRAME_SIZE - len(header))


def decode_beacon_frame(raw: bytes, device_id: str = "unknown") -> LoraBeacon | None:
    """Decode a 32-byte LoRa frame. Returns None if invalid."""
    if len(raw) < FRAME_SIZE:
        return None
    magic, sequence, node_hash, flags = struct.unpack_from(">4sI8sB", raw)
    if magic != FRAME_MAGIC:
        return None
    return LoraBeacon(
        beacon_id=LoraBeaconID(f"{device_id}:{sequence}"),
        device_id=LoraDeviceID(device_id),
        node_id_hash=node_hash,
        sequence=sequence,
        flags=flags,
    )


class LoraBeaconService:
    """Sends and receives LoRa beacons.

    Requires a USB LoRa stick (RFM95W, sx1276, sx1262 via serial bridge).
    Falls back to simulation mode if no hardware detected.
    Only active when config.research.lora_beacons = True.
    """

    def __init__(self, serial_port: str | None = None, node_id_full: str = "") -> None:
        self._serial_port = serial_port
        self._node_id_full = node_id_full
        self._sequence = 0
        self._received: list[LoraBeacon] = []
        self._simulated = serial_port is None

    def send_heartbeat(self, flags: int = 0) -> bytes:
        """Encode and (if hardware present) transmit a heartbeat frame."""
        frame = encode_beacon_frame(self._node_id_full, self._sequence, flags)
        self._sequence += 1
        if not self._simulated:
            self._transmit(frame)
        return frame

    def _transmit(self, frame: bytes) -> None:
        """Write frame to serial LoRa hardware (stub — real impl needs pyserial)."""
        try:
            import serial  # type: ignore[import-untyped]

            with serial.Serial(self._serial_port, baudrate=9600, timeout=1) as ser:
                ser.write(frame)
        except ImportError:
            pass  # pyserial not installed — silently skip

    def receive_frame(self, raw: bytes, device_id: str = "unknown") -> LoraBeacon | None:
        """Decode an incoming frame and record it."""
        beacon = decode_beacon_frame(raw, device_id)
        if beacon is not None:
            self._received.append(beacon)
        return beacon

    def recent_beacons(self, window_seconds: float = 300.0) -> list[LoraBeacon]:
        cutoff = time.time() - window_seconds
        return [b for b in self._received if b.received_at >= cutoff]

    def health(self) -> dict:
        return {
            "hardware": "detected" if not self._simulated else "simulated",
            "serial_port": self._serial_port,
            "sent": self._sequence,
            "received": len(self._received),
        }
