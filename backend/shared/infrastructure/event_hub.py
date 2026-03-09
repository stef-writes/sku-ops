"""In-process event hub for broadcasting domain events to WebSocket clients.

Thin pub/sub layer using asyncio queues. Domain contexts emit events through
the module-level ``emit()`` function. The WebSocket transport subscribes via
``subscribe()`` and forwards events to connected clients.

This intentionally avoids Redis or any external broker — a single-process
event bus is sufficient for a single-instance deployment. If horizontal
scaling is needed later, swap the internal set of queues for a Redis
pub/sub or Postgres LISTEN/NOTIFY backend.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Event:
    type: str
    org_id: str
    data: dict[str, Any] = field(default_factory=dict)
    user_id: str = ""


SHUTDOWN = Event(type="__shutdown__", org_id="")
"""Sentinel event pushed to a subscriber queue to signal the sender to exit."""


def is_shutdown(event: Event) -> bool:
    return event.type == "__shutdown__"


class _Hub:
    """Manages subscriber queues and broadcasts events."""

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[Event]] = set()

    def subscribe(self) -> asyncio.Queue[Event]:
        q: asyncio.Queue[Event] = asyncio.Queue(maxsize=256)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[Event]) -> None:
        self._subscribers.discard(q)

    async def emit(self, event_type: str, *, org_id: str, user_id: str = "", **data: Any) -> None:
        event = Event(type=event_type, org_id=org_id, data=data, user_id=user_id)
        dead: list[asyncio.Queue[Event]] = []
        for q in self._subscribers:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                dead.append(q)
                logger.warning("Dropping slow WebSocket subscriber (queue full)")
        for q in dead:
            self._subscribers.discard(q)
            try:
                q.get_nowait()
            except asyncio.QueueEmpty:
                pass
            try:
                q.put_nowait(SHUTDOWN)
            except asyncio.QueueFull:
                pass


_hub = _Hub()

subscribe = _hub.subscribe
unsubscribe = _hub.unsubscribe
emit = _hub.emit
