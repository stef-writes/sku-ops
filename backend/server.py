"""
Supply Yard API - Material Management System.
Main entry point: composes FastAPI app with routers from api package.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware

from shared.infrastructure.logging_config import setup_logging

setup_logging()

import logging

from shared.infrastructure.config import CORS_ORIGINS, cors_warn_in_deployed, is_deployed, is_test
from shared.infrastructure.database import init_db, close_db
from kernel.errors import DomainError
from shared.infrastructure.middleware.request_id import RequestIDMiddleware
from shared.infrastructure.middleware.security_headers import SecurityHeadersMiddleware
from shared.infrastructure.middleware.rate_limit import setup_rate_limiting
from shared.infrastructure.metrics import setup_sentry, setup_prometheus
from api import api_router
from scripts.seed import seed_mock_user, seed_standard_departments

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize DB and seed data on startup; close DB on shutdown."""
    if cors_warn_in_deployed:
        logger.warning("CORS_ORIGINS is permissive (*). Set CORS_ORIGINS explicitly for staging/production.")
    await init_db()
    logger.info("Database initialized")
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
    for seed_fn in (seed_mock_user, seed_standard_departments):
        try:
            await seed_fn()
        except Exception as e:
            logger.warning(f"Seed {seed_fn.__name__}: {e}")
    try:
        from assistant.agents.tools.search import get_index
        await get_index("default")
    except Exception as e:
        logger.warning(f"BM25 index warm-up skipped: {e}")
    yield
    await close_db()


app = FastAPI(lifespan=lifespan)
app.include_router(api_router)

setup_sentry()
setup_prometheus(app)

# ── Exception handlers ────────────────────────────────────────────────────────

@app.exception_handler(DomainError)
async def domain_error_handler(request, exc: DomainError):
    return JSONResponse(status_code=exc.status_hint, content={"detail": str(exc)})


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
