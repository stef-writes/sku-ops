"""Integration test fixtures — TestClient with portal for org-scoped operations.

Integration tests use the real ASGI app via TestClient. This ensures
org_id_var / user_id_var are correctly set through the request lifecycle
(auth middleware), avoiding the pytest-asyncio contextvar propagation
issue that occurs when setting contextvars in async fixtures.

For tests that call domain functions directly (not through HTTP), use
the ``call`` fixture which wraps portal.call() with org context.
"""

import pytest
from starlette.testclient import TestClient

from tests.helpers.auth import admin_headers, contractor_headers


async def _truncate_and_seed():
    """Truncate all tables and seed minimal data for test isolation."""
    from shared.infrastructure.database import get_connection
    from shared.infrastructure.logging_config import org_id_var, user_id_var

    conn = get_connection()
    await conn.execute(
        """DO $$
        DECLARE r RECORD;
        BEGIN
            FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public') LOOP
                EXECUTE 'TRUNCATE TABLE ' || quote_ident(r.tablename) || ' CASCADE';
            END LOOP;
        END $$"""
    )
    await conn.commit()

    org_id_var.set("default")
    user_id_var.set("user-1")

    await conn.execute(
        """INSERT INTO organizations (id, name, slug, created_at)
           VALUES ('default', 'Default', 'default', NOW())
           ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name"""
    )
    await conn.execute(
        """INSERT INTO departments (id, name, code, description, sku_count, organization_id, created_at)
           VALUES ('dept-1', 'Hardware', 'HDW', 'Hardware dept', 0, 'default', NOW())
           ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name"""
    )
    await conn.execute(
        """INSERT INTO users (id, email, password, name, role, is_active, organization_id, created_at)
           VALUES ('user-1', 'test@test.com', 'hash', 'Test User', 'admin', 1, 'default', NOW())
           ON CONFLICT (id) DO UPDATE SET email = EXCLUDED.email"""
    )
    await conn.execute(
        """INSERT INTO users (id, email, password, name, role, company, billing_entity, is_active, organization_id, created_at)
           VALUES ('contractor-1', 'contractor@test.com', 'hash', 'Contractor User', 'contractor', 'ACME', 'ACME Inc', 1, 'default', NOW())
           ON CONFLICT (id) DO UPDATE SET email = EXCLUDED.email"""
    )
    await conn.commit()


@pytest.fixture(scope="session")
def _integration_client():
    """Session-scoped TestClient — app boots once for all integration tests."""
    from server import app

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


@pytest.fixture(autouse=True)
def _clean_db(_integration_client):
    """Truncate and seed before each test for isolation."""
    _integration_client.portal.call(_truncate_and_seed)


@pytest.fixture
def client(_integration_client):
    """Per-test alias for the TestClient."""
    return _integration_client


@pytest.fixture
def auth():
    """Admin auth headers."""
    return admin_headers()


@pytest.fixture
def contractor_auth():
    """Contractor auth headers."""
    return contractor_headers()


@pytest.fixture
def call(_integration_client):
    """Execute an async callable in the ASGI event loop with org context.

    Usage::

        def test_something(call):
            async def _body():
                result = await some_async_fn()
                assert result is not None

            call(_body)
    """

    def _call(async_fn):
        async def _with_ctx():
            from shared.infrastructure.logging_config import org_id_var, user_id_var

            org_id_var.set("default")
            user_id_var.set("user-1")
            return await async_fn()

        return _integration_client.portal.call(_with_ctx)

    return _call
