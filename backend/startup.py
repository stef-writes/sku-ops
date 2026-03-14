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
    RESET_DB,
    cors_warn_in_deployed,
    is_deployed,
    is_test,
)
from shared.infrastructure.database import close_db, init_db
from shared.infrastructure.logging_config import org_id_var
from shared.infrastructure.redis import close_redis, init_redis, is_redis_available
from shared.kernel.constants import DEFAULT_ORG_ID

logger = logging.getLogger(__name__)


async def _reset_db() -> None:
    """Drop all application tables so init_db() recreates them clean.

    Used when RESET_DB=true is set in the environment. Intended for demo
    environments where all data is synthetic and a full wipe is acceptable.
    Tables are dropped in reverse FK dependency order to avoid constraint errors.
    """
    from shared.infrastructure.db import drop_all_tables

    logger.warning("RESET_DB=true — dropping all tables for a clean restart")
    await drop_all_tables()
    logger.warning("RESET_DB: all tables dropped — schema will be recreated on init_db()")


async def _get_active_org_ids() -> list[str]:
    """Return org IDs that should run scheduled jobs."""
    from shared.infrastructure.org_repo import list_all

    orgs = await list_all()
    return [o.id for o in orgs] if orgs else ["default"]


async def _ensure_default_org() -> None:
    """Insert the default organization row if it doesn't exist yet."""
    from datetime import UTC, datetime

    from shared.infrastructure.database import get_connection

    conn = get_connection()
    cursor = await conn.execute("SELECT id FROM organizations WHERE id = ?", (DEFAULT_ORG_ID,))
    if await cursor.fetchone():
        return
    await conn.execute(
        "INSERT INTO organizations (id, name, slug, created_at) VALUES (?, ?, ?, ?)",
        (DEFAULT_ORG_ID, "Default", DEFAULT_ORG_ID, datetime.now(UTC).isoformat()),
    )
    await conn.commit()
    logger.info("Default organization created (id=%s)", DEFAULT_ORG_ID)


async def _ensure_demo_users() -> None:
    """Create admin + contractor demo accounts if they don't already exist."""
    import uuid
    from datetime import UTC, datetime

    import bcrypt

    from shared.infrastructure.config import (
        DEMO_CONTRACTOR_EMAIL,
        DEMO_USER_EMAIL,
        DEMO_USER_PASSWORD,
    )
    from shared.infrastructure.database import get_connection

    def hash_password(pw: str) -> str:
        return bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

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
    conn = get_connection()
    for u in demo_users:
        cursor = await conn.execute("SELECT id FROM users WHERE email = ?", (u["email"],))
        if await cursor.fetchone():
            continue
        await conn.execute(
            "INSERT INTO users (id, email, password, name, role, company, is_active, organization_id, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)",
            (
                str(uuid.uuid4()),
                u["email"],
                hash_password(DEMO_USER_PASSWORD),
                u["name"],
                u["role"],
                u.get("company", ""),
                DEFAULT_ORG_ID,
                datetime.now(UTC).isoformat(),
            ),
        )
        await conn.commit()
        logger.info("Demo user ready: %s / %s (%s)", u["email"], DEMO_USER_PASSWORD, u["role"])


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
    if RESET_DB:
        await _reset_db()

    await init_db()
    logger.info("Database initialized")

    from shared.infrastructure.config import seed_on_startup

    if seed_on_startup:
        token = org_id_var.set(DEFAULT_ORG_ID)
        try:
            await _ensure_default_org()
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

    if is_deployed:
        logger.info(
            "AUTH: JWT_SECRET is configured. If using Supabase Auth, verify this "
            "matches your Supabase project's JWT secret (Dashboard > Settings > API)."
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
