"""End-to-end workflow tests — create entities via HTTP, verify side effects.

Each test exercises a full business workflow through the API layer,
including negative cases and invariant checks.
"""

from tests.helpers.auth import admin_headers, contractor_headers


def _create_product(client, headers, **overrides):
    """Helper — create a product and return its JSON, or raise on failure."""
    data = {
        "name": "Workflow Test Item",
        "price": 10.00,
        "cost": 4.00,
        "quantity": 100,
        "department_id": "dept-1",
        **overrides,
    }
    resp = client.post("/api/products", json=data, headers=headers)
    assert resp.status_code == 200, f"Product create failed: {resp.text}"
    return resp.json()


class TestWithdrawalWorkflow:
    """Withdrawal must decrement stock and produce an invoice."""

    async def test_withdrawal_decrements_stock(self, db, client):
        headers = admin_headers()
        product = _create_product(client, headers, quantity=50, name="WD-Decrement")

        resp = client.post(
            "/api/withdrawals",
            json={
                "items": [
                    {
                        "product_id": product["id"],
                        "sku": product["sku"],
                        "name": product["name"],
                        "quantity": 5,
                        "unit_price": 10.00,
                        "cost": 4.00,
                    }
                ],
                "job_id": "JOB-001",
                "service_address": "123 Test St",
            },
            headers=headers,
        )
        assert resp.status_code == 200
        withdrawal = resp.json()
        assert withdrawal["total"] > 0

        resp = client.get(f"/api/products/{product['id']}", headers=headers)
        assert resp.json()["quantity"] == 45

    async def test_withdrawal_with_insufficient_stock_fails(self, db, client):
        headers = admin_headers()
        product = _create_product(client, headers, quantity=3, name="WD-Insufficient")

        resp = client.post(
            "/api/withdrawals",
            json={
                "items": [
                    {
                        "product_id": product["id"],
                        "sku": product["sku"],
                        "name": product["name"],
                        "quantity": 10,
                        "unit_price": 10.00,
                        "cost": 4.00,
                    }
                ],
                "job_id": "JOB-002",
                "service_address": "456 Fail St",
            },
            headers=headers,
        )
        assert resp.status_code in (400, 422), f"Expected rejection, got {resp.status_code}"

        resp = client.get(f"/api/products/{product['id']}", headers=headers)
        assert resp.json()["quantity"] == 3, "Stock should be unchanged after failed withdrawal"

    async def test_withdrawal_requires_items(self, db, client):
        headers = admin_headers()

        resp = client.post(
            "/api/withdrawals",
            json={"items": [], "job_id": "JOB-003", "service_address": "789 Empty St"},
            headers=headers,
        )
        assert resp.status_code in (400, 422)


class TestMaterialRequestWorkflow:
    """Contractor submits request, admin processes it into a withdrawal."""

    async def test_contractor_request_to_withdrawal(self, db, client):
        admin_h = admin_headers()
        contractor_h = contractor_headers()
        product = _create_product(client, admin_h, name="MR-Workflow")

        resp = client.post(
            "/api/material-requests",
            json={
                "items": [
                    {
                        "product_id": product["id"],
                        "sku": product["sku"],
                        "name": product["name"],
                        "quantity": 3,
                        "unit_price": 10.00,
                        "cost": 4.00,
                    }
                ],
                "notes": "Need for site work",
            },
            headers=contractor_h,
        )
        assert resp.status_code == 200
        mat_req = resp.json()
        assert mat_req["status"] == "pending"

        resp = client.post(
            f"/api/material-requests/{mat_req['id']}/process",
            json={"job_id": "JOB-004", "service_address": "456 Site Rd"},
            headers=admin_h,
        )
        assert resp.status_code == 200
        result = resp.json()
        assert result.get("id"), "Processed result should have a withdrawal id"

    async def test_admin_cannot_create_material_request(self, db, client):
        admin_h = admin_headers()
        product = _create_product(client, admin_h, name="MR-AdminReject")

        resp = client.post(
            "/api/material-requests",
            json={
                "items": [
                    {
                        "product_id": product["id"],
                        "sku": product["sku"],
                        "name": product["name"],
                        "quantity": 1,
                        "unit_price": 10.00,
                        "cost": 4.00,
                    }
                ],
            },
            headers=admin_h,
        )
        assert resp.status_code == 403


class TestProductWorkflow:
    """Product CRUD through the API layer."""

    async def test_create_and_retrieve_product(self, db, client):
        headers = admin_headers()
        product = _create_product(client, headers, name="PW-Create")

        resp = client.get(f"/api/products/{product['id']}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["name"] == "PW-Create"

    async def test_create_product_missing_required_fields(self, db, client):
        headers = admin_headers()

        resp = client.post("/api/products", json={"name": "Incomplete"}, headers=headers)
        assert resp.status_code == 422

    async def test_create_product_invalid_department(self, db, client):
        headers = admin_headers()

        resp = client.post(
            "/api/products",
            json={
                "name": "Bad Dept",
                "price": 10.00,
                "quantity": 1,
                "department_id": "nonexistent-dept",
            },
            headers=headers,
        )
        assert resp.status_code in (400, 404, 422)
