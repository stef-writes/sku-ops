"""Contractors API tests — list, search."""
import pytest_asyncio

from identity.application.auth_service import create_token


@pytest_asyncio.fixture
async def auth_headers():
    return {"Authorization": f"Bearer {create_token('user-1', 'test@test.com', 'admin', 'default')}"}


class TestContractorsList:
    """GET /api/contractors"""

    def test_requires_auth(self, client):
        r = client.get("/api/contractors")
        assert r.status_code in (401, 403)

    def test_list_returns_contractors(self, client, _db, auth_headers):
        """With seeded contractor, list returns at least one."""
        r = client.get("/api/contractors", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        contractor = next((c for c in data if c.get("email") == "contractor@test.com"), None)
        assert contractor is not None
        assert contractor["name"] == "Contractor User"
        assert contractor["company"] == "ACME"

    def test_search_filters_by_name(self, client, _db, auth_headers):
        """search param filters by name, email, company, etc."""
        r = client.get("/api/contractors", params={"search": "Contractor User"}, headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert len(data) >= 1
        assert any(c["name"] == "Contractor User" for c in data)

    def test_search_filters_by_company(self, client, _db, auth_headers):
        r = client.get("/api/contractors", params={"search": "ACME"}, headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert len(data) >= 1
        assert any(c.get("company") == "ACME" for c in data)

    def test_search_empty_when_no_match(self, client, _db, auth_headers):
        r = client.get("/api/contractors", params={"search": "xyznonexistent123"}, headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert data == []
