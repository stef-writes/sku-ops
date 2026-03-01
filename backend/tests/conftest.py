"""Pytest configuration and fixtures."""
import os

import pytest
import pytest_asyncio

# Use in-memory SQLite for tests (set before any db imports)
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["PAYMENT_ADAPTER"] = "stub"
os.environ["JWT_SECRET"] = "test-secret-key-for-pytest"


@pytest_asyncio.fixture
async def db():
    """Initialize in-memory DB, seed minimal data. Cleanup on teardown."""
    from db import init_db, close_db, get_connection
    await init_db()
    conn = get_connection()
    await conn.execute(
        """INSERT OR REPLACE INTO departments (id, name, code, description, product_count, created_at)
           VALUES ('dept-1', 'Hardware', 'HDW', 'Hardware dept', 0, datetime('now'))"""
    )
    await conn.execute(
        """INSERT OR REPLACE INTO users (id, email, password, name, role, is_active, created_at)
           VALUES ('user-1', 'test@test.com', 'hash', 'Test User', 'admin', 1, datetime('now'))"""
    )
    await conn.commit()
    yield
    await close_db()
