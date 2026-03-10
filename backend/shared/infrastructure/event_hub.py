"""Event delivery hub — broadcasts domain events to WebSocket clients.

When Redis is available (production / staging) events are published to a Redis
Pub/Sub channel so every worker receives them.  Without Redis the hub falls
back to in-process asyncio queues (fine for single-worker dev/test).

Domain types (``Event``, ``SHUTDOWN``, ``is_shutdown``) live in
``kernel.events`` — re-exported here for backward compatibility.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from typing import Any

from kernel.events import SHUTDOWN, Event, is_shutdown

logger = logging.getLogger(__name__)

# Re-export so existing ``from shared.infrastructure.event_hub import Event``
# continues to work.
__all__ = [
    "SHUTDOWN",
    "Event",
    "activate_redis",
    "emit",
    "emit_sync",
    "is_shutdown",
    "subscribe",
    "unsubscribe",
]

_CHANNEL = "sku_ops:events"


def _serialize(event: Event) -> str:
    return json.dumps(
        {
            "type": event.type,
            "org_id": event.org_id,
            "user_id": event.user_id,
            "data": event.data,
        }
    )


def _deserialize(raw: str) -> Event:
    d = json.loads(raw)
    return Event(
        type=d["type"], org_id=d["org_id"], user_id=d.get("user_id", ""), data=d.get("data", {})
    )


class _Hub:
    """Manages subscriber queues and broadcasts events."""

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[Event]] = set()
        self._use_redis: bool = False
        self._reader_tasks: dict[int, asyncio.Task] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    # ------------------------------------------------------------------
    # Lifecycle — called once from server.py lifespan after init_redis()
    # ------------------------------------------------------------------

    def activate_redis(self) -> None:
        self._use_redis = True
        logger.info("Event hub: Redis pub/sub enabled")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def subscribe(self) -> asyncio.Queue[Event]:
        q: asyncio.Queue[Event] = asyncio.Queue(maxsize=256)
        self._subscribers.add(q)
        with contextlib.suppress(RuntimeError):
            self._loop = asyncio.get_running_loop()
        if self._use_redis:
            task = asyncio.create_task(self._redis_reader(q))
            self._reader_tasks[id(q)] = task
        return q

    def unsubscribe(self, q: asyncio.Queue[Event]) -> None:
        self._subscribers.discard(q)
        task = self._reader_tasks.pop(id(q), None)
        if task and not task.done():
            task.cancel()

    async def emit(self, event_type: str, *, org_id: str, user_id: str = "", **data: Any) -> None:
        event = Event(type=event_type, org_id=org_id, data=data, user_id=user_id)

        if self._use_redis:
            try:
                from shared.infrastructure.redis import get_redis

                await get_redis().publish(_CHANNEL, _serialize(event))
            except Exception:
                logger.warning("Redis publish failed — broadcasting in-process only", exc_info=True)
                self._broadcast_local(event)
        else:
            self._broadcast_local(event)

    def emit_sync(self, event_type: str, *, org_id: str, user_id: str = "", **data: Any) -> None:
        """Thread-safe synchronous emit — pushes directly to in-process queues.

        Use from background threads, sync endpoints, or test code that runs
        outside the ASGI event loop.  Bypasses Redis (the receiving worker's
        ``_redis_reader`` handles cross-process delivery separately).

        Schedules ``_broadcast_local`` on the event loop that owns the subscriber
        queues so ``asyncio.Queue.get()`` waiters are properly woken.
        """
        event = Event(type=event_type, org_id=org_id, data=data, user_id=user_id)
        loop = self._loop
        if loop is not None and loop.is_running():
            loop.call_soon_threadsafe(self._broadcast_local, event)
        else:
            self._broadcast_local(event)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _broadcast_local(self, event: Event) -> None:
        """Push event to all in-process subscriber queues."""
        dead: list[asyncio.Queue[Event]] = []
        for q in self._subscribers:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                dead.append(q)
                logger.warning("Dropping slow WebSocket subscriber (queue full)")
        for q in dead:
            self._subscribers.discard(q)
            with contextlib.suppress(asyncio.QueueEmpty):
                q.get_nowait()
            with contextlib.suppress(asyncio.QueueFull):
                q.put_nowait(SHUTDOWN)

    async def _redis_reader(self, q: asyncio.Queue[Event]) -> None:
        """Subscribe to the Redis channel and forward messages to *q*."""
        from shared.infrastructure.redis import get_redis

        pubsub = get_redis().pubsub()
        try:
            await pubsub.subscribe(_CHANNEL)
            while True:
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if msg is None:
                    continue
                if msg["type"] != "message":
                    continue
                try:
                    event = _deserialize(msg["data"])
                except (json.JSONDecodeError, KeyError):
                    continue
                if q not in self._subscribers:
                    return
                try:
                    q.put_nowait(event)
                except asyncio.QueueFull:
                    self._subscribers.discard(q)
                    with contextlib.suppress(asyncio.QueueEmpty):
                        q.get_nowait()
                    with contextlib.suppress(asyncio.QueueFull):
                        q.put_nowait(SHUTDOWN)
                    return
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.warning("Redis reader died — subscriber will not receive events", exc_info=True)
        finally:
            with contextlib.suppress(Exception):
                await pubsub.unsubscribe(_CHANNEL)
                await pubsub.aclose()


_hub = _Hub()

subscribe = _hub.subscribe
unsubscribe = _hub.unsubscribe
emit = _hub.emit
emit_sync = _hub.emit_sync
activate_redis = _hub.activate_redis
