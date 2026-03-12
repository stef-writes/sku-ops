"""Auth endpoint tests — login, /me, register."""

import pytest


class TestLogin:
    """POST /api/auth/login"""

    def test_login_no_db_returns_503_or_401(self, client):
        """Without DB init the login route must not crash — 503 or 401 acceptable."""
        r = client.post(
            "/api/auth/login",
            json={"email": "nobody@nowhere.com", "password": "x"},
        )
        assert r.status_code in (401, 503)

    def test_login_missing_fields_returns_422(self, client):
        r = client.post("/api/auth/login", json={"email": "x@x.com"})
        assert r.status_code == 422

    @pytest.mark.usefixtures("_db_with_bcrypt_user")
    def test_login_wrong_password(self, client):
        r = client.post(
            "/api/auth/login",
            json={"email": "bcrypt@test.com", "password": "wrong"},
        )
        assert r.status_code == 401

    @pytest.mark.usefixtures("_db_with_bcrypt_user")
    def test_login_correct_password_returns_token_and_user(self, client):
        r = client.post(
            "/api/auth/login",
            json={"email": "bcrypt@test.com", "password": "secret123"},
        )
        assert r.status_code == 200
        data = r.json()
        assert "token" in data
        assert data["user"]["email"] == "bcrypt@test.com"
        assert data["user"]["role"] == "admin"
        assert "password" not in data["user"]


class TestMe:
    """GET /api/auth/me"""

    def test_me_requires_auth(self, client):
        r = client.get("/api/auth/me")
        assert r.status_code in (401, 403)

    @pytest.mark.usefixtures("_db")
    def test_me_returns_user_profile(self, client, auth_headers):
        r = client.get("/api/auth/me", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["email"] == "test@test.com"
        assert data["role"] == "admin"
        assert "password" not in data

    def test_me_with_invalid_token_returns_401(self, client):
        r = client.get("/api/auth/me", headers={"Authorization": "Bearer invalid.token"})
        assert r.status_code == 401


class TestRegister:
    """POST /api/auth/register"""

    @pytest.mark.usefixtures("_db")
    def test_register_creates_user_and_returns_token(self, client):
        r = client.post(
            "/api/auth/register",
            json={"email": "new@test.com", "password": "pass123", "name": "New User"},
        )
        assert r.status_code == 200
        data = r.json()
        assert "token" in data
        assert data["user"]["email"] == "new@test.com"
        assert data["user"]["role"] == "admin"

    @pytest.mark.usefixtures("_db")
    def test_register_duplicate_email_returns_409(self, client):
        r = client.post(
            "/api/auth/register",
            json={"email": "test@test.com", "password": "x", "name": "Dupe"},
        )
        assert r.status_code == 409

    def test_register_missing_fields_returns_422(self, client):
        r = client.post("/api/auth/register", json={"email": "x@x.com"})
        assert r.status_code == 422
