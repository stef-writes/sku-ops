"""Application lifespan — init, seed, warm-up, shutdown.

Owns everything that happens between process start and first request,
and between last response and process exit.
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

from scheduler import xero_sync_loop
from shared.infrastructure.config import (
    DEFAULT_ORG_ID,
    cors_warn_in_deployed,
    is_deployed,
    is_test,
)
from shared.infrastructure.database import close_db, init_db
from shared.infrastructure.logging_config import org_id_var
from shared.infrastructure.redis import close_redis, init_redis, is_redis_available

logger = logging.getLogger(__name__)


async def _get_active_org_ids() -> list[str]:
    """Return org IDs that should run scheduled jobs."""
    from identity.infrastructure.org_repo import list_all

    orgs = await list_all()
    return [o.id for o in orgs] if orgs else ["default"]


async def _ensure_demo_users() -> None:
    """Create admin + contractor demo accounts if they don't already exist."""
    import uuid
    from datetime import UTC, datetime

    from identity.application.auth_service import hash_password
    from identity.infrastructure.user_repo import get_by_email, insert
    from shared.infrastructure.config import (
        DEMO_CONTRACTOR_EMAIL,
        DEMO_USER_EMAIL,
        DEMO_USER_PASSWORD,
    )

    demo_users = [
        {"email": DEMO_USER_EMAIL, "name": "Admin", "role": "admin"},
    ]
    if DEMO_CONTRACTOR_EMAIL:
        demo_users.append(
            {
                "email": DEMO_CONTRACTOR_EMAIL,
                "name": "Demo Contractor",
                "role": "contractor",
                "company": "ABC Plumbing",
            }
        )
    for u in demo_users:
        existing = await get_by_email(u["email"])
        if existing:
            continue
        await insert(
            {
                "id": str(uuid.uuid4()),
                "email": u["email"],
                "password": hash_password(DEMO_USER_PASSWORD),
                "name": u["name"],
                "role": u["role"],
                "company": u.get("company", ""),
                "is_active": True,
                "organization_id": DEFAULT_ORG_ID,
                "created_at": datetime.now(UTC).isoformat(),
            }
        )
        logger.info("Created demo user: %s (%s)", u["email"], u["role"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize DB and seed data on startup; close DB on shutdown."""
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
            "CORS_ORIGINS is permissive (*). Set CORS_ORIGINS explicitly for staging/production."
        )
    await init_db()
    logger.info("Database initialized")

    from shared.infrastructure.config import seed_on_startup

    if seed_on_startup:
        token = org_id_var.set(DEFAULT_ORG_ID)
        try:
            await _ensure_demo_users()
        finally:
            org_id_var.reset(token)

    from assistant.infrastructure.llm import init_llm

    init_llm()
    logger.info("LLM provider initialized")
    from assistant.agents.tools.registry import init_tools

    init_tools()
    logger.info("Tool registry initialized")
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

    from shared.infrastructure.config import (
        ANTHROPIC_AVAILABLE,
        DATABASE_URL,
        OPENAI_AVAILABLE,
        SENTRY_DSN,
    )

    db_type = "postgres" if "postgresql" in (DATABASE_URL or "") else "sqlite"
    logger.info(
        "Application ready — env=%s, db=%s, sentry=%s, ai=%s, embeddings=%s",
        "production" if is_deployed else ("test" if is_test else "development"),
        db_type,
        "enabled" if SENTRY_DSN else "disabled",
        "enabled" if ANTHROPIC_AVAILABLE else "disabled",
        "enabled" if OPENAI_AVAILABLE else "disabled",
    )

    ws_routes = [r.path for r in app.routes if hasattr(r, "path") and r.path.startswith("/api/ws")]
    assert "/api/ws" in ws_routes, "Domain event WebSocket not mounted"
    assert "/api/ws/chat" in ws_routes, "Chat streaming WebSocket not mounted"
    logger.info("WebSocket endpoints verified: %s", ws_routes)

    from shared.infrastructure.database import get_connection

    conn = get_connection()
    await conn.execute("SELECT 1")
    logger.info("Database connectivity verified")

    from assistant.agents.tools.search import (
        start_invalidation_listener,
        stop_invalidation_listener,
    )

    sync_task = None
    if not is_test:
        sync_task = asyncio.create_task(xero_sync_loop())
        start_invalidation_listener()

    yield

    await stop_invalidation_listener()
    if sync_task is not None:
        sync_task.cancel()
        with suppress(asyncio.CancelledError):
            await sync_task
    await close_db()
    await close_redis()
