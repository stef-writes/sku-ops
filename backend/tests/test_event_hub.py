"""Tests for the in-process event hub (pub/sub)."""
import asyncio

import pytest

from shared.infrastructure.event_hub import Event, _Hub


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

    async def test_full_queue_drops_slow_subscriber(self):
        hub = _Hub()
        q = hub.subscribe()
        for i in range(256):
            await hub.emit("flood", org_id="org-1", i=i)
        assert q.full()
        await hub.emit("overflow", org_id="org-1")
        assert q not in hub._subscribers

    async def test_event_is_frozen_dataclass(self):
        event = Event(type="t", org_id="o")
        with pytest.raises(AttributeError):
            event.type = "changed"
