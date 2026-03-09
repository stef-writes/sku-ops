"""Tests for the chat session store — covers the in-process fallback path
and, when REDIS_URL is set, the Redis hash path.
"""
import os

import pytest

from assistant.application import session_store

_REDIS_URL = os.environ.get("REDIS_URL", "")


class TestSessionStoreFallback:
    """Tests the dict-based fallback (no Redis)."""

    async def test_get_or_create_returns_empty_list(self):
        history = await session_store.get_or_create("test-new")
        assert history == []
        await session_store.clear("test-new")

    async def test_update_and_retrieve(self):
        sid = "test-update"
        await session_store.update(sid, [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ], cost_usd=0.05)

        history = await session_store.get_or_create(sid)
        assert len(history) == 2
        assert history[0]["content"] == "hello"

        cost = await session_store.get_cost(sid)
        assert cost == pytest.approx(0.05)
        await session_store.clear(sid)

    async def test_cost_accumulates(self):
        sid = "test-cost"
        await session_store.update(sid, [], cost_usd=0.10)
        await session_store.update(sid, [], cost_usd=0.25)
        cost = await session_store.get_cost(sid)
        assert cost == pytest.approx(0.35)
        await session_store.clear(sid)

    async def test_clear_removes_session(self):
        sid = "test-clear"
        await session_store.update(sid, [{"role": "user", "content": "x"}])
        await session_store.clear(sid)
        cost = await session_store.get_cost(sid)
        assert cost == 0.0

    async def test_history_windowing(self):
        sid = "test-window"
        long_history = [{"role": "user" if i % 2 == 0 else "assistant", "content": str(i)} for i in range(100)]
        await session_store.update(sid, long_history)
        history = await session_store.get_or_create(sid)
        assert len(history) == 40  # _MAX_TURNS=20 → 40 messages
        await session_store.clear(sid)

    async def test_get_cost_nonexistent(self):
        cost = await session_store.get_cost("nonexistent-sid")
        assert cost == 0.0


@pytest.mark.skipif(not _REDIS_URL, reason="Redis not available")
class TestSessionStoreRedis:
    """Tests the Redis hash path — only runs when a local Redis is reachable."""

    async def _setup_redis(self):
        from shared.infrastructure.redis import init_redis
        await init_redis()

    async def _teardown_redis(self):
        from shared.infrastructure.redis import close_redis
        await close_redis()

    async def test_crud_via_redis(self):
        await self._setup_redis()
        try:
            sid = "redis-test-crud"

            history = await session_store.get_or_create(sid)
            assert history == []

            await session_store.update(sid, [
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "hello"},
            ], cost_usd=0.10)

            history = await session_store.get_or_create(sid)
            assert len(history) == 2
            assert history[0]["content"] == "hi"

            cost = await session_store.get_cost(sid)
            assert cost == pytest.approx(0.10)

            await session_store.clear(sid)
            cost = await session_store.get_cost(sid)
            assert cost == 0.0
        finally:
            await self._teardown_redis()

    async def test_cost_accumulates_via_redis(self):
        await self._setup_redis()
        try:
            sid = "redis-test-cost-accum"
            await session_store.update(sid, [], cost_usd=0.05)
            await session_store.update(sid, [], cost_usd=0.15)
            cost = await session_store.get_cost(sid)
            assert cost == pytest.approx(0.20)
            await session_store.clear(sid)
        finally:
            await self._teardown_redis()

    async def test_windowing_via_redis(self):
        await self._setup_redis()
        try:
            sid = "redis-test-window"
            long = [{"role": "user" if i % 2 == 0 else "assistant", "content": str(i)} for i in range(100)]
            await session_store.update(sid, long)
            history = await session_store.get_or_create(sid)
            assert len(history) == 40
            await session_store.clear(sid)
        finally:
            await self._teardown_redis()
