"""Health and readiness endpoints for orchestration probes."""

import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.routing import WebSocketRoute

from shared.infrastructure.config import (
    _ENV,
    ANTHROPIC_AVAILABLE,
    ANTHROPIC_MODEL,
    LLM_SETUP_URL,
    OPENROUTER_AVAILABLE,
)
from shared.infrastructure.database import get_connection

router = APIRouter(tags=["health"])

_BOOT_TIME = time.monotonic()
_APP_VERSION = "0.1.0"


@router.get("/health")
async def health():
    """Liveness probe — returns 200 if the process is running.

    Includes uptime and environment for quick operational triage.
    """
    return {
        "status": "ok",
        "version": _APP_VERSION,
        "env": _ENV,
        "uptime_seconds": round(time.monotonic() - _BOOT_TIME),
    }


@router.get("/ready")
async def ready(request: Request):
    """Readiness probe — returns 200 only if DB and core services are reachable."""
    checks: dict = {}
    overall = "ok"

    try:
        conn = get_connection()
        t0 = time.perf_counter()
        await conn.execute("SELECT 1")
        checks["database"] = {
            "status": "ok",
            "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
        }
    except (RuntimeError, OSError) as exc:
        checks["database"] = {"status": "unavailable", "error": str(exc)}
        overall = "unavailable"

    ai_ok = ANTHROPIC_AVAILABLE or OPENROUTER_AVAILABLE
    checks["ai"] = {"status": "ok" if ai_ok else "unconfigured"}

    expected_ws = {"/api/ws", "/api/ws/chat"}
    mounted_ws = [r.path for r in request.app.routes if isinstance(r, WebSocketRoute)]
    ws_ok = expected_ws.issubset(set(mounted_ws))
    checks["websocket"] = {
        "status": "ok" if ws_ok else "missing",
        "endpoints": mounted_ws,
    }

    status_code = 200 if overall == "ok" else 503
    return JSONResponse(
        status_code=status_code,
        content={"status": overall, "checks": checks},
    )


@router.get("/health/ai")
async def ai_health():
    """AI availability probe."""
    if not ANTHROPIC_AVAILABLE:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unavailable",
                "detail": f"ANTHROPIC_API_KEY not set. Get a key at {LLM_SETUP_URL}",
            },
        )
    return {"status": "ok", "provider": "anthropic", "model": ANTHROPIC_MODEL}
