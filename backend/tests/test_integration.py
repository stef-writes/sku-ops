"""
Integration smoke tests.

Uses the in-process TestClient (no network, no live DB needed for auth checks).
The `client` fixture from conftest.py initialises the FastAPI app without starting
the full lifespan (so init_db is not called) — auth rejection (401) happens before
any DB access, making these tests safe and fast.
"""
import pytest

# ── Endpoint tables ───────────────────────────────────────────────────────────

# (method, path) pairs that must reject unauthenticated requests.
# Organised by bounded context so missing routers are immediately visible.
PROTECTED_ENDPOINTS = [
    # identity
    ("GET",  "/api/auth/me"),
    # catalog
    ("GET",  "/api/products"),
    ("GET",  "/api/vendors"),
    ("GET",  "/api/departments"),
    # operations
    ("GET",  "/api/withdrawals"),
    ("GET",  "/api/material-requests"),
    # purchasing
    ("GET",  "/api/purchase-orders"),
    # finance
    ("GET",  "/api/invoices"),
    ("GET",  "/api/financials/summary"),
    # assistant
    ("POST", "/api/chat"),
]


# ── No-auth endpoints ─────────────────────────────────────────────────────────

def test_root_endpoint(client):
    """API root returns 200 and a message."""
    response = client.get("/api/")
    assert response.status_code == 200
    assert "message" in response.json()


def test_health_liveness(client):
    """/health liveness probe returns 200 without auth or DB."""
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json().get("status") == "ok"


def test_ai_health_configured(client):
    """/health/ai returns 200 when ANTHROPIC_API_KEY is set (conftest sets a dummy key)."""
    response = client.get("/api/health/ai")
    assert response.status_code == 200


# ── Auth enforcement ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("method,path", PROTECTED_ENDPOINTS)
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
    A 404 means the router was never registered.
    """
    context_probes = {
        "identity":   ("GET",  "/api/auth/me"),
        "catalog":    ("GET",  "/api/products"),
        "operations": ("GET",  "/api/withdrawals"),
        "purchasing": ("GET",  "/api/purchase-orders"),
        "finance":    ("GET",  "/api/invoices"),
        "documents":  ("POST", "/api/documents/parse"),
        "assistant":  ("POST", "/api/chat"),
        "reports":    ("GET",  "/api/health"),
    }
    not_mounted = []
    for ctx, (method, path) in context_probes.items():
        resp = client.request(method, path, json={})
        if resp.status_code == 404:
            not_mounted.append(f"{ctx}: {method} {path}")

    assert not not_mounted, (
        "These context routers appear unmounted (got 404):\n"
        + "\n".join(f"  {m}" for m in not_mounted)
    )
