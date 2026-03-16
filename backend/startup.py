"""Application lifespan — init, warm-up, shutdown.

Owns everything that happens between process start and first request,
and between last response and process exit.
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager, suppress
from urllib.parse import urlparse

from fastapi import FastAPI

from scheduler import xero_sync_loop
from shared.infrastructure.config import (
    DATABASE_URL,
    cors_warn_in_deployed,
    db_is_local,
    is_deployed,
    is_development,
    is_test,
    startup_summary,
)
from shared.infrastructure.database import close_db, init_db
from shared.infrastructure.redis import close_redis, init_redis, is_redis_available

logger = logging.getLogger(__name__)


async def _get_active_org_ids() -> list[str]:
    """Return org IDs that should run scheduled jobs."""
    from shared.infrastructure.org_repo import list_all

    orgs = await list_all()
    return [o.id for o in orgs] if orgs else []


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize DB on startup; close DB on shutdown."""
    worker_count = int(os.environ.get("WORKERS", "1"))

    await init_redis()
    if is_redis_available():
        from shared.infrastructure.event_hub import activate_redis

        activate_redis()
        if worker_count > 1:
            logger.info("WORKERS=%d — Redis is connected, multi-worker mode is safe", worker_count)
    elif worker_count > 1:
        raise RuntimeError(
            f"WORKERS={worker_count} but REDIS_URL is not set. "
            "Multi-worker mode requires Redis for event hub, sessions, and sync locks. "
            "Set REDIS_URL or use WORKERS=1."
        )

    if cors_warn_in_deployed:
        logger.warning(
            "CORS_ORIGINS is permissive (*). Set CORS_ORIGINS explicitly for production."
        )

    await init_db()
    logger.info("Database initialized")

    if is_development and not db_is_local:
        _host = urlparse(DATABASE_URL).hostname or "<unknown>"
        logger.warning(
            "DATABASE_URL points at a non-local host ('%s') while ENV=development. "
            "Development mode enables ALLOW_RESET and public auth endpoints. "
            "If this is intentional, set ENV=production instead.",
            _host,
        )

    import assistant.agents.tools.search  # noqa: F401 — registers index invalidation handler
    import finance.application.event_handlers  # noqa: F401
    import inventory.application.event_handlers  # noqa: F401
    import shared.infrastructure.ws_bridge  # noqa: F401

    logger.info("Domain event handlers registered")

    from assistant.infrastructure.llm import init_llm

    init_llm()
    logger.info("LLM provider initialized")
    from assistant.agents.tools.registry import init_tools

    init_tools()
    logger.info("Tool registry initialized")

    try:
        from assistant.agents.tools.tool_index import get_tool_index

        idx = get_tool_index()
        await idx.rebuild()
        logger.info("Tool index rebuilt (%d tools)", len(idx._names))
    except (RuntimeError, OSError, ValueError) as e:
        logger.warning("Tool index warm-up skipped: %s", e)

    async def _background_warmup() -> None:
        from shared.infrastructure.logging_config import org_id_var

        org_ids = await _get_active_org_ids()
        for oid in org_ids:
            token = org_id_var.set(oid)
            try:
                from assistant.agents.tools.search import get_index

                await get_index()
            except (RuntimeError, OSError, ValueError) as e:
                logger.warning("BM25 index warm-up skipped for org '%s': %s", oid, e)
            try:
                from finance.application.xero_startup_check import run_startup_check

                await run_startup_check()
            except (RuntimeError, OSError, ValueError) as e:
                logger.warning("Xero startup check failed for org '%s': %s", oid, e)
            finally:
                org_id_var.reset(token)

    warmup_task = asyncio.create_task(_background_warmup())

    summary = startup_summary()
    logger.info("Application ready — %s", summary)
    if summary.get("flags"):
        logger.warning(
            "Active permissive flags: %s — review before deploying to production",
            ", ".join(summary["flags"]),
        )
    if is_deployed:
        logger.info(
            "AUTH: JWT_SECRET is configured. If using Supabase Auth, verify this "
            "matches your Supabase project's JWT secret (Dashboard > Settings > API)."
        )

    ws_routes = [r.path for r in app.routes if hasattr(r, "path") and r.path.startswith("/api/ws")]
    assert "/api/ws" in ws_routes, "Domain event WebSocket not mounted"
    assert "/api/ws/chat" in ws_routes, "Chat streaming WebSocket not mounted"
    logger.info("WebSocket endpoints verified: %s", ws_routes)

    from shared.infrastructure.database import transaction

    async with transaction() as conn:
        await conn.execute("SELECT 1")
    logger.info("Database connectivity verified")

    sync_task = None
    if not is_test:
        sync_task = asyncio.create_task(xero_sync_loop())

    yield

    warmup_task.cancel()
    with suppress(asyncio.CancelledError):
        await warmup_task
    if sync_task is not None:
        sync_task.cancel()
        with suppress(asyncio.CancelledError):
            await sync_task
    await close_db()
    await close_redis()
