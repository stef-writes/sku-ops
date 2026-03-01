"""
Supply Yard API - Material Management System.
Main entry point: composes FastAPI app with routers from api package.
"""
import os
from pathlib import Path

# Load .env from backend/ before any other imports
_path = Path(__file__).resolve().parent
if (_path / ".env").exists():
    from dotenv import load_dotenv

    load_dotenv(_path / ".env")

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

import logging

from db import init_db, close_db
from domain.exceptions import InsufficientStockError, ResourceNotFoundError
from api import api_router
from api.seed import seed_mock_user, seed_standard_departments, seed_demo_inventory

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI()
app.include_router(api_router)


@app.exception_handler(ResourceNotFoundError)
async def resource_not_found_handler(request, exc: ResourceNotFoundError):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(InsufficientStockError)
async def insufficient_stock_handler(request, exc: InsufficientStockError):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=400, content={"detail": str(exc)})

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    """Initialize SQLite database and seed data on startup."""
    try:
        await init_db()
        logger.info("Database initialized")
        await seed_mock_user()
        await seed_standard_departments()
        await seed_demo_inventory()
    except Exception as e:
        logger.warning(f"Database init: {e}")


@app.on_event("shutdown")
async def shutdown_db_client():
    await close_db()
