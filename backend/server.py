"""
Supply Yard API - Material Management System.
Main entry point: composes FastAPI app with routers from api package.
"""
from contextlib import asynccontextmanager

from shared.infrastructure.config import CORS_ORIGINS, cors_warn_in_deployed
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware

import logging

from shared.infrastructure.database import init_db, close_db
from shared.domain.exceptions import InsufficientStockError, ResourceNotFoundError
from api import api_router
from identity.api.seed import seed_mock_user, seed_standard_departments

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize DB and seed data on startup; close DB on shutdown."""
    if cors_warn_in_deployed:
        logger.warning("CORS_ORIGINS is permissive (*). Set CORS_ORIGINS explicitly for staging/production.")
    await init_db()
    logger.info("Database initialized")
    for seed_fn in (seed_mock_user, seed_standard_departments):
        try:
            await seed_fn()
        except Exception as e:
            logger.warning(f"Seed {seed_fn.__name__}: {e}")
    try:
        from services.agents.search import get_index
        await get_index("default")
    except Exception as e:
        logger.warning(f"BM25 index warm-up skipped: {e}")
    yield
    await close_db()


app = FastAPI(lifespan=lifespan)
app.include_router(api_router)


@app.exception_handler(ResourceNotFoundError)
async def resource_not_found_handler(request, exc: ResourceNotFoundError):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(InsufficientStockError)
async def insufficient_stock_handler(request, exc: InsufficientStockError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=CORS_ORIGINS.split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)
