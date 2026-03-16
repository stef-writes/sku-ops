"""Root pytest configuration — environment variables and shared fixtures.

All backend tests run against Postgres. The test database (sku_ops_test)
is auto-created by ``./bin/dev db``. A single session-scoped TestClient
boots the ASGI app once; sub-directory conftest files add fixtures
specific to their scope (e.g. DB seeding, auth helpers).
"""

import os

os.environ["ENV"] = "test"
# CI injects DATABASE_URL (:5432). Local dev: docker-compose binds host :5433→container :5432.
os.environ.setdefault("DATABASE_URL", "postgresql://sku_ops:localdev@localhost:5433/sku_ops_test")
os.environ.setdefault("REDIS_URL", "")
os.environ.setdefault("JWT_SECRET", "test-" + "secret-key-for-pytest-32bytes!")
os.environ.setdefault(
    "ANTHROPIC_API_KEY", ""
)  # intentionally empty — ANTHROPIC_AVAILABLE=False in tests


import pytest

import finance.application.event_handlers  # noqa: F401 — registers domain event handlers
import inventory.application.event_handlers  # noqa: F401
import shared.infrastructure.ws_bridge  # noqa: F401
from tests.helpers.events import EventCollector

# ── Session-scoped app client ────────────────────────────────────────────────


@pytest.fixture(scope="session")
def _app_client():
    """Session-scoped TestClient — boots the ASGI app once for the entire test run.

    All test directories share this single client so that init_db/close_db
    lifecycle is consistent (no pool corruption from overlapping lifespans).
    """
    from starlette.testclient import TestClient

    from server import app

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


# ── DB seeding helpers (run inside the app event loop via portal.call) ────────


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
           ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, slug = EXCLUDED.slug"""
    )
    await conn.execute(
        """INSERT INTO departments (id, name, code, description, sku_count, organization_id, created_at)
           VALUES ('dept-1', 'Hardware', 'HDW', 'Hardware dept', 0, 'default', NOW())
           ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, code = EXCLUDED.code,
           description = EXCLUDED.description, sku_count = EXCLUDED.sku_count,
           organization_id = EXCLUDED.organization_id"""
    )
    await conn.execute(
        """INSERT INTO users (id, email, password, name, role, is_active, organization_id, created_at)
           VALUES ('user-1', 'test@test.com', 'hash', 'Test User', 'admin', 1, 'default', NOW())
           ON CONFLICT (id) DO UPDATE SET email = EXCLUDED.email, password = EXCLUDED.password,
           name = EXCLUDED.name, role = EXCLUDED.role, is_active = EXCLUDED.is_active,
           organization_id = EXCLUDED.organization_id"""
    )
    await conn.execute(
        """INSERT INTO users (id, email, password, name, role, company, billing_entity,
           is_active, organization_id, created_at)
           VALUES ('contractor-1', 'contractor@test.com', 'hash', 'Contractor User',
           'contractor', 'ACME', 'ACME Inc', 1, 'default', NOW())
           ON CONFLICT (id) DO UPDATE SET email = EXCLUDED.email, password = EXCLUDED.password,
           name = EXCLUDED.name, role = EXCLUDED.role, company = EXCLUDED.company,
           billing_entity = EXCLUDED.billing_entity, is_active = EXCLUDED.is_active,
           organization_id = EXCLUDED.organization_id"""
    )
    await conn.commit()


# ── Shared fixtures ──────────────────────────────────────────────────────────


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
