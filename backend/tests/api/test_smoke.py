"""Smoke tests — health probes, auth enforcement, router mounting.

These run without DB and verify the API surface is correctly wired.
"""

import pytest

from tests.helpers.auth import admin_headers

PROTECTED_ENDPOINTS = [
    ("GET", "/api/catalog/skus"),
    ("GET", "/api/catalog/skus/by-barcode"),
    ("GET", "/api/vendors"),
    ("GET", "/api/departments"),
    ("GET", "/api/withdrawals"),
    ("GET", "/api/material-requests"),
    ("GET", "/api/purchase-orders"),
    ("GET", "/api/invoices"),
    ("GET", "/api/financials/summary"),
    ("POST", "/api/chat"),
    ("GET", "/api/audit-log"),
    ("GET", "/api/dashboard/stats"),
    ("GET", "/api/dashboard/transactions"),
]


# ── Auth enforcement ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(("method", "path"), PROTECTED_ENDPOINTS)
def test_endpoint_requires_auth(client, method, path):
    """Every protected endpoint must reject unauthenticated requests with 401 or 403."""
    response = client.request(method, path, json={})
    assert response.status_code in (401, 403), (
        f"{method} {path} returned {response.status_code} — "
        "expected 401/403 for unauthenticated request"
    )


# ── Router mount verification ─────────────────────────────────────────────────


def test_all_context_routers_mounted(client):
    """
    Verify every bounded context router is mounted by checking that a known
    endpoint returns 401/403 (auth required) rather than 404 (route not found).
    """
    context_probes = {
        "catalog": ("GET", "/api/catalog/skus"),
        "operations": ("GET", "/api/withdrawals"),
        "purchasing": ("GET", "/api/purchase-orders"),
        "finance": ("GET", "/api/invoices"),
        "documents": ("POST", "/api/documents/parse"),
        "assistant": ("POST", "/api/chat"),
        "health": ("GET", "/api/health"),
    }
    not_mounted = []
    for ctx, (method, path) in context_probes.items():
        resp = client.request(method, path, json={})
        if resp.status_code == 404:
            not_mounted.append(f"{ctx}: {method} {path}")

    assert not not_mounted, "These context routers appear unmounted (got 404):\n" + "\n".join(
        f"  {m}" for m in not_mounted
    )


# ── Auth endpoint surface ─────────────────────────────────────────────────────


def test_auth_me_requires_auth(client):
    """/api/auth/me must reject unauthenticated requests."""
    resp = client.get("/api/auth/me")
    assert resp.status_code in (401, 403), (
        f"GET /api/auth/me returned {resp.status_code} — expected 401/403"
    )


def test_auth_login_endpoint_exists(client):
    """POST /api/auth/login must be mounted (returns 4xx, not 404)."""
    resp = client.post("/api/auth/login", json={"email": "x@x.com", "password": "wrong"})
    assert resp.status_code != 404, "POST /api/auth/login is not mounted"


def test_auth_register_endpoint_exists(client):
    """POST /api/auth/register must be mounted (returns 4xx, not 404)."""
    resp = client.post(
        "/api/auth/register", json={"email": "x@x.com", "password": "pw", "name": "X"}
    )
    assert resp.status_code != 404, "POST /api/auth/register is not mounted"


def test_auth_me_with_valid_token(client):
    """/api/auth/me with a valid token must not 404 or 500."""
    resp = client.get("/api/auth/me", headers=admin_headers())
    assert resp.status_code not in (404, 500), (
        f"GET /api/auth/me with valid token returned unexpected {resp.status_code}"
    )
