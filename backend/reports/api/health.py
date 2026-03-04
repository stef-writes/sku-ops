"""Health and readiness endpoints for orchestration probes."""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from shared.infrastructure.config import ANTHROPIC_AVAILABLE, ANTHROPIC_MODEL, LLM_SETUP_URL
from shared.infrastructure.database import get_connection

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    """Liveness probe - returns 200 if the process is running."""
    return {"status": "ok"}


@router.get("/ready")
async def ready():
    """Readiness probe - returns 200 if DB is reachable, 503 otherwise."""
    try:
        conn = get_connection()
        await conn.execute("SELECT 1")
        return {"status": "ok"}
    except Exception:
        return JSONResponse(
            status_code=503,
            content={"status": "unavailable", "detail": "Database unreachable"},
        )


@router.get("/health/ai")
async def ai_health():
    """AI availability probe. Returns 200 if Anthropic is configured, 503 otherwise."""
    if not ANTHROPIC_AVAILABLE:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unavailable",
                "detail": f"ANTHROPIC_API_KEY not set. Get a key at {LLM_SETUP_URL}",
            },
        )
    return {"status": "ok", "provider": "anthropic", "model": ANTHROPIC_MODEL}
