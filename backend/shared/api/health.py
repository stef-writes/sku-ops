"""Health and readiness endpoints for orchestration probes."""

import asyncio
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from shared.infrastructure.config import (
    AGENT_PRIMARY_MODEL,
    ANTHROPIC_AVAILABLE,
    ENV,
    LLM_SETUP_URL,
    OPENROUTER_AVAILABLE,
    REDIS_URL,
)
from shared.infrastructure.database import transaction

router = APIRouter(tags=["health"])

_BOOT_TIME = time.monotonic()
_APP_VERSION = "0.1.0"
_NO_CACHE = {"Cache-Control": "no-store"}

_DB_TIMEOUT_S = 3.0


@router.get("/health")
async def health():
    """Liveness probe — returns 200 if the process is running."""
    return JSONResponse(
        content={
            "status": "ok",
            "version": _APP_VERSION,
            "env": ENV,
            "uptime_seconds": round(time.monotonic() - _BOOT_TIME),
        },
        headers=_NO_CACHE,
    )


@router.get("/ready")
async def ready(request: Request):
    """Readiness probe — returns 200 only if DB and core services are reachable."""
    checks: dict = {}
    overall = "ok"

    # --- database (with timeout) ---
    try:
        t0 = time.perf_counter()
        async with asyncio.timeout(_DB_TIMEOUT_S):
            async with transaction() as conn:
                await conn.execute("SELECT 1")
        checks["database"] = {
            "status": "ok",
            "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
        }
    except TimeoutError:
        checks["database"] = {"status": "unavailable", "error": "timeout"}
        overall = "unavailable"
    except (RuntimeError, OSError) as exc:
        checks["database"] = {"status": "unavailable", "error": str(exc)}
        overall = "unavailable"

    # --- redis (only when configured) ---
    if REDIS_URL:
        try:
            from shared.infrastructure.redis import get_redis, is_redis_available

            if not is_redis_available():
                checks["redis"] = {"status": "unavailable", "error": "not initialised"}
                overall = "unavailable"
            else:
                t0 = time.perf_counter()
                async with asyncio.timeout(_DB_TIMEOUT_S):
                    await get_redis().ping()
                checks["redis"] = {
                    "status": "ok",
                    "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
                }
        except (TimeoutError, RuntimeError, OSError) as exc:
            checks["redis"] = {"status": "unavailable", "error": str(exc)}
            overall = "unavailable"

    # --- ai ---
    ai_ok = ANTHROPIC_AVAILABLE or OPENROUTER_AVAILABLE
    checks["ai"] = {"status": "ok" if ai_ok else "unconfigured"}

    status_code = 200 if overall == "ok" else 503
    return JSONResponse(
        status_code=status_code,
        content={"status": overall, "checks": checks},
        headers=_NO_CACHE,
    )


@router.get("/health/ai")
async def ai_health():
    """AI availability probe."""
    if not ANTHROPIC_AVAILABLE and not OPENROUTER_AVAILABLE:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unavailable",
                "detail": f"No LLM API key configured. Set ANTHROPIC_API_KEY or OPENROUTER_API_KEY. Get a key at {LLM_SETUP_URL}",
            },
            headers=_NO_CACHE,
        )
    provider = "openrouter" if OPENROUTER_AVAILABLE else "anthropic"
    return JSONResponse(
        content={"status": "ok", "provider": provider, "agent_model": AGENT_PRIMARY_MODEL},
        headers=_NO_CACHE,
    )
