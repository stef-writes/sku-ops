"""Pytest configuration and fixtures."""
import os

import pytest
import pytest_asyncio
from starlette.testclient import TestClient

# Test environment: set before any app/config imports
os.environ["ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["JWT_SECRET"] = "test-secret-key-for-pytest-32bytes!"
# Provide a dummy key so pydantic-ai can instantiate Agent at import time.
# Tests that exercise LLM paths mock the actual API calls.
os.environ.setdefault("ANTHROPIC_API_KEY", "test-dummy-key-not-real")


@pytest.fixture
def client():
    """HTTP client for in-process API tests (no network)."""
    from server import app
    return TestClient(app)


@pytest_asyncio.fixture
async def db():
    """Initialize in-memory DB, seed minimal data. Cleanup on teardown."""
    from shared.infrastructure.database import close_db, get_connection, init_db
    await init_db()
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

    # Wire cross-domain DI (server.py does this in lifespan; tests bypass lifespan)
    from finance.infrastructure.invoice_repo import set_withdrawal_getter
    from operations.application.queries import get_withdrawal_by_id
    set_withdrawal_getter(get_withdrawal_by_id)

    yield
    await close_db()
