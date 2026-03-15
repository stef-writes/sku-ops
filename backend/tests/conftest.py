"""Root pytest configuration — environment variables and shared fixtures.

All backend tests run against Postgres. The test database (sku_ops_test)
is auto-created by ``./bin/dev db``. Fixtures initialize the schema via
init_db() and seed minimal data. Sub-directory conftest files may add
fixtures specific to their scope (e.g. HTTP client for api tests).
"""

import os

os.environ["ENV"] = "test"
os.environ.setdefault("DATABASE_URL", "postgresql://sku_ops:localdev@localhost:5432/sku_ops_test")
os.environ.setdefault("REDIS_URL", "")
os.environ.setdefault("JWT_SECRET", "test-" + "secret-key-for-pytest-32bytes!")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-dummy-key-not-real")


import pytest
import pytest_asyncio

import finance.application.event_handlers  # noqa: F401 — registers domain event handlers
import inventory.application.event_handlers  # noqa: F401
import shared.infrastructure.ws_bridge  # noqa: F401
from shared.infrastructure.logging_config import org_id_var, user_id_var
from tests.helpers.events import EventCollector


@pytest_asyncio.fixture
async def db():
    """Initialize Postgres test DB, seed minimal data. Cleanup on teardown."""
    from shared.infrastructure.database import close_db, get_connection, init_db

    await init_db()
    org_id_var.set("default")
    user_id_var.set("user-1")
    conn = get_connection()
    await conn.execute(
        """INSERT INTO organizations (id, name, slug, created_at)
           VALUES ('default', 'Default', 'default', NOW())
           ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, slug = EXCLUDED.slug"""
    )
    await conn.execute(
        """INSERT INTO departments (id, name, code, description, sku_count, organization_id, created_at)
           VALUES ('dept-1', 'Hardware', 'HDW', 'Hardware dept', 0, 'default', NOW())
           ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, code = EXCLUDED.code, description = EXCLUDED.description, sku_count = EXCLUDED.sku_count, organization_id = EXCLUDED.organization_id"""
    )
    await conn.execute(
        """INSERT INTO users (id, email, password, name, role, is_active, organization_id, created_at)
           VALUES ('user-1', 'test@test.com', 'hash', 'Test User', 'admin', 1, 'default', NOW())
           ON CONFLICT (id) DO UPDATE SET email = EXCLUDED.email, password = EXCLUDED.password, name = EXCLUDED.name, role = EXCLUDED.role, is_active = EXCLUDED.is_active, organization_id = EXCLUDED.organization_id"""
    )
    await conn.execute(
        """INSERT INTO users (id, email, password, name, role, company, billing_entity, is_active, organization_id, created_at)
           VALUES ('contractor-1', 'contractor@test.com', 'hash', 'Contractor User', 'contractor', 'ACME', 'ACME Inc', 1, 'default', NOW())
           ON CONFLICT (id) DO UPDATE SET email = EXCLUDED.email, password = EXCLUDED.password, name = EXCLUDED.name, role = EXCLUDED.role, company = EXCLUDED.company, billing_entity = EXCLUDED.billing_entity, is_active = EXCLUDED.is_active, organization_id = EXCLUDED.organization_id"""
    )
    await conn.commit()
    yield
    await close_db()


@pytest_asyncio.fixture
async def _db(db):
    """Alias for ``db`` — many test files reference this name."""
    yield


@pytest.fixture
def event_collector():
    """Capture all domain events dispatched during a test.

    Wraps ``dispatch`` so the real handlers still run, but every event is
    also recorded in the collector for later assertion.
    """
    from unittest.mock import patch

    from shared.infrastructure.domain_events import dispatch as real_dispatch

    collector = EventCollector()

    async def _capturing_dispatch(event):
        await collector.capture(event)
        await real_dispatch(event)

    with patch("shared.infrastructure.domain_events.dispatch", side_effect=_capturing_dispatch):
        yield collector


@pytest_asyncio.fixture
async def _db_with_bcrypt_user(db):
    """DB with a user whose password is a real bcrypt hash (for auth endpoint tests)."""
    import bcrypt

    from shared.infrastructure.database import get_connection

    hashed = bcrypt.hashpw(b"secret123", bcrypt.gensalt()).decode("utf-8")
    conn = get_connection()
    await conn.execute(
        "INSERT INTO users "
        "(id, email, password, name, role, is_active, organization_id, created_at) "
        "VALUES ('bcrypt-user-1', 'bcrypt@test.com', $1, 'Bcrypt User', 'admin', 1, 'default', NOW()) "
        "ON CONFLICT (id) DO UPDATE SET password = EXCLUDED.password",
        (hashed,),
    )
    await conn.commit()
    yield
