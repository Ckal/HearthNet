from __future__ import annotations

import time


class DeliveryManager:
    """Decides direct vs store-and-forward delivery."""

    def __init__(self, bus=None, our_node_id: str = ""):
        self._bus = bus
        self._our_node_id = our_node_id
        self._queued: list[dict] = []  # store-and-forward queue

    async def deliver(self, message: dict, recipient_node_id: str) -> str:
        """Try direct delivery. Returns 'direct', 'queued', or 'self'."""
        if recipient_node_id == self._our_node_id:
            return "self"

        if self._bus is not None:
            try:
                from hearthnet.bus.capability import RouteRequest

                req = RouteRequest(
                    capability="chat.send",
                    version_req=(1, 0),
                    body={"input": message},
                    caller=self._our_node_id,
                    trace_id="",
                )
                entry = self._bus.router.route(req)
                if entry and entry.node_id == recipient_node_id and not entry.is_local:
                    return "direct"
            except Exception:
                pass

        # Store-and-forward
        self._queued.append(
            {
                "message": message,
                "to": recipient_node_id,
                "queued_at": time.time(),
            }
        )
        return "queued"

    def get_queued(self, node_id: str) -> list[dict]:
        return [q for q in self._queued if q["to"] == node_id]

    def acknowledge(self, message_event_id: str) -> None:
        self._queued = [q for q in self._queued if q["message"].get("event_id") != message_event_id]
