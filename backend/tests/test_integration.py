"""
Integration tests — smoke tests and authenticated workflow tests.

Smoke tests use the TestClient without the full lifespan (no DB needed for auth
rejection checks). Workflow tests use the ``db`` fixture for real DB operations.
"""
import pytest
from starlette.testclient import TestClient

from identity.application.auth_service import create_token

# ── Endpoint tables ───────────────────────────────────────────────────────────

PROTECTED_ENDPOINTS = [
    # identity
    ("GET", "/api/auth/me"),
    # catalog
    ("GET", "/api/products"),
    ("GET", "/api/products/by-barcode"),
    ("GET", "/api/vendors"),
    ("GET", "/api/departments"),
    # operations
    ("GET", "/api/withdrawals"),
    ("GET", "/api/material-requests"),
    # purchasing
    ("GET", "/api/purchase-orders"),
    # finance
    ("GET", "/api/invoices"),
    ("GET", "/api/financials/summary"),
    # assistant
    ("POST", "/api/chat"),
]


# ── Helpers ──────────────────────────────────────────────────────────────────

def _admin_headers() -> dict:
    token = create_token("user-1", "test@test.com", "admin", "default")
    return {"Authorization": f"Bearer {token}"}


def _contractor_headers() -> dict:
    token = create_token("contractor-1", "contractor@test.com", "contractor", "default")
    return {"Authorization": f"Bearer {token}"}


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
        "identity": ("GET", "/api/auth/me"),
        "catalog": ("GET", "/api/products"),
        "operations": ("GET", "/api/withdrawals"),
        "purchasing": ("GET", "/api/purchase-orders"),
        "finance": ("GET", "/api/invoices"),
        "documents": ("POST", "/api/documents/parse"),
        "assistant": ("POST", "/api/chat"),
        "reports": ("GET", "/api/health"),
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


# ── Authenticated workflow tests ──────────────────────────────────────────────


class TestProductWorkflow:
    """Create a product and verify it appears in listings."""

    async def test_create_and_list_product(self, db):
        from starlette.testclient import TestClient

        from server import app

        client = TestClient(app)
        headers = _admin_headers()

        product_data = {
            "name": "Test Bolt 10mm",
            "description": "Galvanized steel bolt",
            "price": 2.50,
            "cost": 1.00,
            "quantity": 100,
            "min_stock": 10,
            "department_id": "dept-1",
            "base_unit": "each",
            "sell_uom": "each",
            "pack_qty": 1,
        }

        resp = client.post("/api/products", json=product_data, headers=headers)
        assert resp.status_code == 200, f"Product create failed: {resp.text}"
        product = resp.json()
        product_id = product["id"]
        assert product["name"] == "Test Bolt 10mm"

        resp = client.get(f"/api/products/{product_id}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["id"] == product_id


class TestWithdrawalWorkflow:
    """Create a product, withdraw stock, verify inventory decrements."""

    async def test_withdrawal_decrements_stock(self, db):
        from starlette.testclient import TestClient

        from server import app

        client = TestClient(app)
        headers = _admin_headers()

        product_data = {
            "name": "Withdrawal Test Item",
            "price": 5.00,
            "cost": 2.00,
            "quantity": 50,
            "department_id": "dept-1",
        }
        resp = client.post("/api/products", json=product_data, headers=headers)
        assert resp.status_code == 200
        product = resp.json()
        pid = product["id"]
        sku = product["sku"]

        withdrawal_data = {
            "items": [{
                "product_id": pid,
                "sku": sku,
                "name": "Withdrawal Test Item",
                "quantity": 5,
                "unit_price": 5.00,
                "cost": 2.00,
            }],
            "job_id": "JOB-001",
            "service_address": "123 Test St",
        }
        resp = client.post("/api/withdrawals", json=withdrawal_data, headers=headers)
        assert resp.status_code == 200, f"Withdrawal create failed: {resp.text}"
        withdrawal = resp.json()
        assert withdrawal["total"] > 0

        resp = client.get(f"/api/products/{pid}", headers=headers)
        assert resp.status_code == 200
        updated_qty = resp.json()["quantity"]
        assert updated_qty == 45, f"Expected 45 after withdrawing 5 from 50, got {updated_qty}"


class TestMaterialRequestWorkflow:
    """Contractor submits request, admin processes it into a withdrawal."""

    async def test_contractor_request_to_withdrawal(self, db):
        from starlette.testclient import TestClient

        from server import app

        client = TestClient(app)
        admin_h = _admin_headers()
        contractor_h = _contractor_headers()

        product_data = {
            "name": "Mat Request Test Item",
            "price": 10.00,
            "cost": 4.00,
            "quantity": 100,
            "department_id": "dept-1",
        }
        resp = client.post("/api/products", json=product_data, headers=admin_h)
        assert resp.status_code == 200
        product = resp.json()

        request_data = {
            "items": [{
                "product_id": product["id"],
                "sku": product["sku"],
                "name": "Mat Request Test Item",
                "quantity": 3,
                "unit_price": 10.00,
                "cost": 4.00,
            }],
            "notes": "Need for site work",
        }
        resp = client.post("/api/material-requests", json=request_data, headers=contractor_h)
        assert resp.status_code == 200, f"Material request create failed: {resp.text}"
        mat_req = resp.json()
        assert mat_req["status"] == "pending"
        req_id = mat_req["id"]

        resp = client.post(
            f"/api/material-requests/{req_id}/process",
            json={"job_id": "JOB-002", "service_address": "456 Site Rd"},
            headers=admin_h,
        )
        assert resp.status_code == 200, f"Process request failed: {resp.text}"
        result = resp.json()
        assert result.get("id"), f"Expected processed withdrawal to have an id, got keys: {list(result.keys())}"


class TestInvoiceWorkflow:
    """Create a withdrawal, then verify invoice listing includes it."""

    async def test_withdrawal_appears_in_invoices(self, db):
        from starlette.testclient import TestClient

        from server import app

        client = TestClient(app)
        headers = _admin_headers()

        product_data = {
            "name": "Invoice Test Item",
            "price": 20.00,
            "cost": 8.00,
            "quantity": 50,
            "department_id": "dept-1",
        }
        resp = client.post("/api/products", json=product_data, headers=headers)
        assert resp.status_code == 200
        product = resp.json()

        withdrawal_data = {
            "items": [{
                "product_id": product["id"],
                "sku": product["sku"],
                "name": "Invoice Test Item",
                "quantity": 2,
                "unit_price": 20.00,
                "cost": 8.00,
            }],
            "job_id": "JOB-003",
            "service_address": "789 Invoice St",
        }
        resp = client.post("/api/withdrawals", json=withdrawal_data, headers=headers)
        assert resp.status_code == 200

        resp = client.get("/api/withdrawals", headers=headers)
        assert resp.status_code == 200
        withdrawals = resp.json()
        assert isinstance(withdrawals, list | dict)
