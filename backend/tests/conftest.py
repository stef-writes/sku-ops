"""Root pytest configuration — environment variables and shared fixtures.

All backend tests (unit, integration, api) inherit these fixtures via
pytest's conftest hierarchy. Sub-directory conftest files may add
fixtures specific to their scope (e.g. HTTP client for api tests).
"""

import os

os.environ["ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("REDIS_URL", "")
os.environ["JWT_SECRET"] = "test-" + "secret-key-for-pytest-32bytes!"
os.environ.setdefault("ANTHROPIC_API_KEY", "test-dummy-key-not-real")


import pytest_asyncio

from shared.infrastructure.logging_config import org_id_var, user_id_var


@pytest_asyncio.fixture
async def db():
    """Initialize in-memory DB, seed minimal data. Cleanup on teardown."""
    from shared.infrastructure.database import close_db, get_connection, init_db

    await init_db()
    org_id_var.set("default")
    user_id_var.set("user-1")
    conn = get_connection()
    await conn.execute(
        """INSERT OR REPLACE INTO departments (id, name, code, description, product_count, organization_id, created_at)
           VALUES ('dept-1', 'Hardware', 'HDW', 'Hardware dept', 0, 'default', datetime('now'))"""
    )
    await conn.execute(
        """INSERT OR REPLACE INTO users (id, email, password, name, role, is_active, organization_id, created_at)
           VALUES ('user-1', 'test@test.com', 'hash', 'Test User', 'admin', 1, 'default', datetime('now'))"""
    )
    await conn.execute(
        """INSERT OR REPLACE INTO users (id, email, password, name, role, company, billing_entity, is_active, organization_id, created_at)
           VALUES ('contractor-1', 'contractor@test.com', 'hash', 'Contractor User', 'contractor', 'ACME', 'ACME Inc', 1, 'default', datetime('now'))"""
    )
    await conn.commit()
    yield
    await close_db()


@pytest_asyncio.fixture
async def _db(db):
    """Alias for ``db`` — many test files reference this name."""
    yield
