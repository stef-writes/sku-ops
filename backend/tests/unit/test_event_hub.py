"""Tests for the event hub (pub/sub) — covers the in-process fallback path
and, when REDIS_URL is set, the Redis pub/sub path.
"""

import os

import pytest

from shared.infrastructure.event_hub import _deserialize, _Hub, _serialize
from shared.kernel.events import SHUTDOWN, Event, is_shutdown

_REDIS_URL = os.environ.get("REDIS_URL", "")


class TestEventHub:
    """Unit tests for _Hub pub/sub mechanics."""

    async def test_subscribe_and_emit(self):
        hub = _Hub()
        q = hub.subscribe()
        await hub.emit("inventory.updated", org_id="org-1")
        event = q.get_nowait()
        assert event.type == "inventory.updated"
        assert event.org_id == "org-1"
        assert event.user_id == ""

    async def test_user_scoped_event(self):
        hub = _Hub()
        q = hub.subscribe()
        await hub.emit("chat.tool_call", org_id="org-1", user_id="user-42", tool="search")
        event = q.get_nowait()
        assert event.user_id == "user-42"
        assert event.data["tool"] == "search"

    async def test_multiple_subscribers(self):
        hub = _Hub()
        q1 = hub.subscribe()
        q2 = hub.subscribe()
        await hub.emit("withdrawal.created", org_id="org-1")
        assert q1.qsize() == 1
        assert q2.qsize() == 1

    async def test_unsubscribe(self):
        hub = _Hub()
        q = hub.subscribe()
        hub.unsubscribe(q)
        await hub.emit("test.event", org_id="org-1")
        assert q.empty()

    async def test_full_queue_drops_and_sends_shutdown(self):
        """When a subscriber queue overflows, the hub removes it and injects
        a SHUTDOWN sentinel so the sender task can exit deterministically."""
        hub = _Hub()
        q = hub.subscribe()
        for i in range(256):
            await hub.emit("flood", org_id="org-1", i=i)
        assert q.full()

        await hub.emit("overflow", org_id="org-1")

        assert q not in hub._subscribers
        # Drain the 255 remaining events (one was evicted to make room for SHUTDOWN)
        events = []
        while not q.empty():
            events.append(q.get_nowait())
        last = events[-1]
        assert is_shutdown(last), f"Expected SHUTDOWN sentinel as last event, got {last.type}"

    async def test_shutdown_sentinel_is_recognisable(self):
        assert is_shutdown(SHUTDOWN) is True
        assert is_shutdown(Event(type="inventory.updated", org_id="org-1")) is False

    async def test_event_is_frozen_dataclass(self):
        event = Event(type="t", org_id="o")
        with pytest.raises(AttributeError):
            event.type = "changed"

    async def test_serialize_deserialize_round_trip(self):
        original = Event(
            type="inventory.updated", org_id="org-1", user_id="u-1", data={"ids": [1, 2]}
        )
        raw = _serialize(original)
        restored = _deserialize(raw)
        assert restored.type == original.type
        assert restored.org_id == original.org_id
        assert restored.user_id == original.user_id
        assert restored.data == original.data

    async def test_serialize_shutdown_round_trip(self):
        raw = _serialize(SHUTDOWN)
        restored = _deserialize(raw)
        assert is_shutdown(restored)


@pytest.mark.skipif(not _REDIS_URL, reason="Redis not available")
class TestEventHubRedis:
    """Tests the Redis pub/sub path — only runs when a local Redis is reachable."""

    async def test_publish_and_receive_via_redis(self):
        """Emit an event through Redis and verify a subscriber receives it."""
        import asyncio

        from shared.infrastructure.redis import close_redis, init_redis

        await init_redis()
        try:
            hub = _Hub()
            hub.activate_redis()
            q = hub.subscribe()

            await asyncio.sleep(0.2)

            await hub.emit("inventory.updated", org_id="org-redis", ids=["p-1"])

            event = await asyncio.wait_for(q.get(), timeout=3.0)
            assert event.type == "inventory.updated"
            assert event.org_id == "org-redis"
            assert event.data["ids"] == ["p-1"]

            hub.unsubscribe(q)
        finally:
            await close_redis()

    async def test_multiple_subscribers_via_redis(self):
        """Two subscribers should both receive the same event via Redis."""
        import asyncio

        from shared.infrastructure.redis import close_redis, init_redis

        await init_redis()
        try:
            hub = _Hub()
            hub.activate_redis()
            q1 = hub.subscribe()
            q2 = hub.subscribe()

            await asyncio.sleep(0.2)

            await hub.emit("test.multi", org_id="org-r2")

            ev1 = await asyncio.wait_for(q1.get(), timeout=3.0)
            ev2 = await asyncio.wait_for(q2.get(), timeout=3.0)
            assert ev1.type == "test.multi"
            assert ev2.type == "test.multi"

            hub.unsubscribe(q1)
            hub.unsubscribe(q2)
        finally:
            await close_redis()
