"""API test fixtures — uses the root session-scoped TestClient.

The DB is truncated and seeded before each test via portal.call()
for proper isolation.
"""

import pytest

from tests.helpers.auth import admin_headers, contractor_headers


@pytest.fixture(autouse=True)
def _clean_db(_app_client):
    """Truncate and seed before each test for isolation."""
    from tests.conftest import _truncate_and_seed

    _app_client.portal.call(_truncate_and_seed)


@pytest.fixture
def client(_app_client):
    """Per-test alias for the session-scoped TestClient."""
    return _app_client


@pytest.fixture
def db(_clean_db):
    """Legacy alias — DB is now auto-cleaned by _clean_db."""
    return


@pytest.fixture
def _db(_clean_db):
    """Legacy alias — DB is now auto-cleaned by _clean_db."""
    return


@pytest.fixture
def _db_with_bcrypt_user(db, _app_client):
    """DB with a user whose password is a real bcrypt hash."""
    import bcrypt

    from shared.infrastructure.database import get_connection

    async def _seed():
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

    _app_client.portal.call(_seed)


@pytest.fixture
def auth_headers():
    """Admin auth headers."""
    return admin_headers()


@pytest.fixture
def contractor_auth_headers():
    """Contractor auth headers."""
    return contractor_headers()
