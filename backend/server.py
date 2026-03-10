"""
Supply Yard API - Material Management System.
Main entry point: composes FastAPI app with routers from api package.

Multi-worker support:
  When REDIS_URL is set, the event hub, chat session store, and Xero sync
  lock use Redis — safe to run with WORKERS > 1.  Without Redis (local dev)
  all subsystems fall back to in-process memory and WORKERS must be 1.
"""

import asyncio
import logging
import os
import traceback
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware

from shared.infrastructure.logging_config import setup_logging

setup_logging()

from datetime import UTC

from api import api_router
from inventory.domain.errors import InsufficientStockError
from kernel.errors import DomainError
from shared.infrastructure.config import (
    CORS_ORIGINS,
    DEFAULT_ORG_ID,
    XERO_SYNC_HOUR,
    cors_warn_in_deployed,
    is_deployed,
    is_test,
)
from shared.infrastructure.database import close_db, init_db
from shared.infrastructure.middleware.rate_limit import setup_rate_limiting
from shared.infrastructure.middleware.request_id import RequestIDMiddleware
from shared.infrastructure.middleware.security_headers import (
    SecurityHeadersMiddleware,
)
from shared.infrastructure.prometheus import setup_prometheus
from shared.infrastructure.redis import close_redis, init_redis, is_redis_available
from shared.infrastructure.sentry import setup_sentry

logger = logging.getLogger(__name__)


async def _get_active_org_ids() -> list[str]:
    """Return org IDs that should run scheduled jobs.

    Currently returns ["default"]. When multi-org is needed, query the
    organizations table for active orgs instead.
    """
    return ["default"]


async def _xero_sync_loop() -> None:
    """Background task: run the Xero sync job once per day at XERO_SYNC_HOUR UTC.

    Wakes up every minute, checks whether the target hour has arrived, and
    fires run_sync for each active org exactly once per calendar day.
    Skipped in test environment.
    """
    from datetime import datetime

    last_run_date = None
    logger.info("Xero nightly sync scheduler started (fires at %02d:00 UTC)", XERO_SYNC_HOUR)
    while True:
        try:
            await asyncio.sleep(60)
            now = datetime.now(UTC)
            if now.hour == XERO_SYNC_HOUR and now.date() != last_run_date:
                last_run_date = now.date()
                org_ids = await _get_active_org_ids()
                for org_id in org_ids:
                    logger.info("Xero nightly sync starting for org '%s'", org_id)
                    try:
                        from finance.application.xero_sync_job import run_sync

                        summary = await run_sync(org_id)
                        logger.info(
                            "Xero nightly sync complete for org '%s': %s",
                            org_id,
                            {k: v for k, v in summary.items() if k != "errors"},
                        )
                        if summary.get("errors"):
                            logger.warning(
                                "Xero nightly sync for org '%s' had %d error(s): %s",
                                org_id,
                                len(summary["errors"]),
                                summary["errors"],
                            )
                    except Exception:
                        logger.exception("Xero nightly sync failed for org '%s'", org_id)
        except asyncio.CancelledError:
            logger.info("Xero nightly sync scheduler stopped")
            return
        except Exception:
            logger.exception("Unexpected error in Xero sync loop")


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
        await _ensure_demo_users()

    from assistant.infrastructure.llm import init_llm

    init_llm()
    logger.info("LLM provider initialized")
    from assistant.agents.tools.registry import init_tools

    init_tools()
    logger.info("Tool registry initialized")
    from finance.infrastructure.invoice_repo import set_withdrawal_getter
    from operations.application.queries import get_withdrawal_by_id

    set_withdrawal_getter(get_withdrawal_by_id)
    logger.info("Cross-domain DI wired")

    org_ids = await _get_active_org_ids()
    for org_id in org_ids:
        try:
            from assistant.agents.tools.search import get_index

            await get_index(org_id)
        except (RuntimeError, OSError, ValueError) as e:
            logger.warning("BM25 index warm-up skipped for org '%s': %s", org_id, e)
        try:
            from finance.application.xero_startup_check import run_startup_check

            await run_startup_check(org_id)
        except (RuntimeError, OSError, ValueError) as e:
            logger.warning("Xero startup check failed for org '%s': %s", org_id, e)

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

    # ── Startup assertions: fail fast on misconfiguration ──
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
        sync_task = asyncio.create_task(_xero_sync_loop())
        start_invalidation_listener()

    yield

    await stop_invalidation_listener()
    if sync_task is not None:
        sync_task.cancel()
        with suppress(asyncio.CancelledError):
            await sync_task
    await close_db()
    await close_redis()


app = FastAPI(lifespan=lifespan)
app.include_router(api_router)

from shared.api.websocket import mount_websocket

mount_websocket(app)

from assistant.api.ws_chat import mount_chat_websocket

mount_chat_websocket(app)

setup_sentry()
setup_prometheus(app)

# ── Exception handlers ────────────────────────────────────────────────────────


@app.exception_handler(InsufficientStockError)
async def insufficient_stock_handler(_request, exc: InsufficientStockError):
    return JSONResponse(
        status_code=exc.status_hint,
        content={
            "detail": str(exc),
            "error_type": "insufficient_stock",
            "sku": exc.sku,
            "requested": exc.requested,
            "available": exc.available,
        },
    )


@app.exception_handler(DomainError)
async def domain_error_handler(_request, exc: DomainError):
    return JSONResponse(status_code=exc.status_hint, content={"detail": str(exc)})


@app.exception_handler(ValueError)
async def value_error_handler(request, exc: ValueError):
    logger.warning("ValueError on %s %s: %s", request.method, request.url.path, exc)
    detail = str(exc) if not is_deployed else "Invalid request"
    return JSONResponse(status_code=400, content={"detail": detail})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc: Exception):
    logger.error(
        "Unhandled %s on %s %s:\n%s",
        type(exc).__name__,
        request.method,
        request.url.path,
        traceback.format_exc(),
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# ── Middleware (outermost first → executes first on request) ──────────────────

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=CORS_ORIGINS.split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestIDMiddleware)

if not is_test:
    setup_rate_limiting(app)
