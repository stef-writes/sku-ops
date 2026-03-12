"""API test fixtures — HTTP client and auth headers."""

import pytest
from starlette.testclient import TestClient

from tests.helpers.auth import admin_headers, contractor_headers


@pytest.fixture
def client():
    """HTTP client for in-process API tests (no network)."""
    from server import app

    return TestClient(app)


@pytest.fixture
def auth_headers():
    """Admin auth headers."""
    return admin_headers()


@pytest.fixture
def contractor_auth_headers():
    """Contractor auth headers."""
    return contractor_headers()
