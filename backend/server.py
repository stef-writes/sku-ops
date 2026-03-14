"""Supply Yard API — composition root.

Creates the FastAPI app, mounts routers, wires middleware and exception
handlers.  Lifespan (init/shutdown) lives in startup.py; background jobs
in scheduler.py.
"""

import logging
import traceback

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware

from shared.infrastructure.logging_config import setup_logging

setup_logging()

from inventory.domain.errors import InsufficientStockError
from routes import api_router
from shared.infrastructure.config import CORS_ORIGINS, is_deployed, is_test
from shared.infrastructure.middleware.rate_limit import setup_rate_limiting
from shared.infrastructure.middleware.request_id import RequestIDMiddleware
from shared.infrastructure.middleware.security_headers import SecurityHeadersMiddleware
from shared.infrastructure.prometheus import setup_prometheus
from shared.infrastructure.sentry import setup_sentry
from shared.kernel.errors import DomainError
from startup import lifespan

logger = logging.getLogger(__name__)

app = FastAPI(lifespan=lifespan)
app.include_router(api_router)

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
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc: Exception):
    logger.error(
        "Unhandled %s on %s %s:\n%s",
        type(exc).__name__,
        request.method,
        request.url.path,
        traceback.format_exc(),
    )
    detail = "Internal server error" if is_deployed else f"{type(exc).__name__}: {exc}"
    return JSONResponse(status_code=500, content={"detail": detail})


# ── Middleware (outermost first → executes first on request) ──────────────────

from shared.infrastructure.config import CORS_ORIGIN_REGEX

_cors_origins = [o.strip() for o in CORS_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=_cors_origins,
    allow_origin_regex=CORS_ORIGIN_REGEX or None,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestIDMiddleware)

if not is_test:
    setup_rate_limiting(app)
