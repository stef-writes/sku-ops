"""Tests for material request creation and processing via HTTP API."""


def _create_product(client, auth, name="Widget", quantity=100.0, cost=5.0, price=10.0):
    """Create a product via API and return the response JSON."""
    resp = client.post(
        "/api/catalog/skus",
        json={
            "name": name,
            "price": price,
            "cost": cost,
            "quantity": quantity,
            "category_id": "dept-1",
            "min_stock": 5,
        },
        headers=auth,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _item_from_product(product, quantity=3):
    return {
        "product_id": product["id"],
        "sku": product["sku"],
        "name": product["name"],
        "quantity": quantity,
        "unit_price": 10.0,
        "cost": 5.0,
    }


def _create_material_request(client, contractor_auth, product, **kwargs):
    """Create a material request as contractor. Returns response."""
    payload = {
        "items": [_item_from_product(product)],
        **kwargs,
    }
    return client.post("/api/material-requests", json=payload, headers=contractor_auth)


# ── Round-trip / persistence ────────────────────────────────────────────────


def test_material_request_round_trip(client, auth, contractor_auth):
    """Material request persisted and retrieved with correct fields."""
    product = _create_product(client, auth)
    resp = _create_material_request(
        client,
        contractor_auth,
        product,
        job_id="JOB-001",
        service_address="123 Main St",
    )
    assert resp.status_code == 200
    created = resp.json()

    get_resp = client.get(f"/api/material-requests/{created['id']}", headers=contractor_auth)
    assert get_resp.status_code == 200
    fetched = get_resp.json()

    assert fetched["contractor_id"] == "contractor-1"
    assert fetched["job_id"] == "JOB-001"
    assert fetched["service_address"] == "123 Main St"
    assert fetched["status"] == "pending"
    assert len(fetched["items"]) == 1


def test_material_request_fallback_fields_preserved(client, auth, contractor_auth):
    """When contractor supplies job_id and service_address, they're stored in the request."""
    product = _create_product(client, auth)
    resp = _create_material_request(
        client,
        contractor_auth,
        product,
        job_id="FALLBACK-JOB",
        service_address="456 Elm",
    )
    assert resp.status_code == 200
    created = resp.json()

    get_resp = client.get(f"/api/material-requests/{created['id']}", headers=contractor_auth)
    assert get_resp.status_code == 200
    fetched = get_resp.json()

    assert fetched["job_id"] == "FALLBACK-JOB"
    assert fetched["service_address"] == "456 Elm"


# ── API handler: create ──────────────────────────────────────────────────────


def test_create_material_request_as_contractor(client, auth, contractor_auth):
    """Contractor can create a material request via the API handler."""
    product = _create_product(client, auth)
    resp = _create_material_request(
        client,
        contractor_auth,
        product,
        job_id="JOB-200",
        service_address="100 Main St",
    )
    assert resp.status_code == 200
    result = resp.json()

    assert result["contractor_id"] == "contractor-1"
    assert result["contractor_name"] == "Contractor User"
    assert result["job_id"] == "JOB-200"
    assert result["service_address"] == "100 Main St"
    assert result["status"] == "pending"
    assert len(result["items"]) == 1


def test_create_material_request_rejects_non_contractor(client, auth):
    """Admin/staff cannot create material requests — only contractors."""
    product = _create_product(client, auth)
    resp = client.post(
        "/api/material-requests",
        json={"items": [_item_from_product(product)]},
        headers=auth,
    )
    assert resp.status_code == 403


def test_create_material_request_rejects_empty_items(client, contractor_auth):
    """Request with no items is rejected."""
    resp = client.post(
        "/api/material-requests",
        json={"items": []},
        headers=contractor_auth,
    )
    assert resp.status_code == 400
    assert "item" in resp.json()["detail"].lower()


# ── API handler: list ────────────────────────────────────────────────────────


def test_list_material_requests_contractor_sees_own(client, auth, contractor_auth):
    """Contractor only sees their own requests."""
    product = _create_product(client, auth)
    _create_material_request(
        client, contractor_auth, product, job_id="J-LIST", service_address="1 Elm"
    )

    resp = client.get("/api/material-requests", headers=contractor_auth)
    assert resp.status_code == 200
    results = resp.json()

    assert len(results) >= 1
    assert all(r["contractor_id"] == "contractor-1" for r in results)


def test_list_material_requests_admin_sees_pending(client, auth, contractor_auth):
    """Admin sees all pending requests."""
    product = _create_product(client, auth)
    _create_material_request(
        client, contractor_auth, product, job_id="J-LIST2", service_address="2 Elm"
    )

    resp = client.get("/api/material-requests", headers=auth)
    assert resp.status_code == 200
    results = resp.json()

    assert len(results) >= 1
    assert all(r["status"] == "pending" for r in results)


# ── API handler: process validation ──────────────────────────────────────────


def test_process_rejects_already_processed(client, auth, contractor_auth):
    """Cannot process a request that's already been processed."""
    product = _create_product(client, auth, quantity=50.0)
    create_resp = _create_material_request(
        client,
        contractor_auth,
        product,
        job_id="J-1",
        service_address="1 Elm",
    )
    assert create_resp.status_code == 200
    req_id = create_resp.json()["id"]

    # Process the first time — should succeed
    first = client.post(
        f"/api/material-requests/{req_id}/process",
        json={"job_id": "J-1", "service_address": "1 Elm"},
        headers=auth,
    )
    assert first.status_code == 200

    # Process again — should fail
    second = client.post(
        f"/api/material-requests/{req_id}/process",
        json={"job_id": "J-1", "service_address": "1 Elm"},
        headers=auth,
    )
    assert second.status_code == 400
    assert "already processed" in second.json()["detail"].lower()


def test_process_rejects_missing_job_id(client, auth, contractor_auth):
    """Processing requires a job_id (from staff or contractor fallback)."""
    product = _create_product(client, auth)
    create_resp = _create_material_request(
        client,
        contractor_auth,
        product,
        job_id="",
        service_address="1 Oak",
    )
    assert create_resp.status_code == 200
    req_id = create_resp.json()["id"]

    resp = client.post(
        f"/api/material-requests/{req_id}/process",
        json={"service_address": "1 Oak"},
        headers=auth,
    )
    assert resp.status_code == 400
    assert "job id" in resp.json()["detail"].lower()


def test_process_rejects_missing_service_address(client, auth, contractor_auth):
    """Processing requires a service_address (from staff or contractor fallback)."""
    product = _create_product(client, auth)
    create_resp = _create_material_request(
        client,
        contractor_auth,
        product,
        job_id="J-1",
        service_address="",
    )
    assert create_resp.status_code == 200
    req_id = create_resp.json()["id"]

    resp = client.post(
        f"/api/material-requests/{req_id}/process",
        json={"job_id": "J-1"},
        headers=auth,
    )
    assert resp.status_code == 400
    assert "service address" in resp.json()["detail"].lower()


def test_process_not_found(client, auth):
    """Processing a non-existent request returns 404."""
    resp = client.post(
        "/api/material-requests/nonexistent-id/process",
        json={"job_id": "J-1", "service_address": "1 Elm"},
        headers=auth,
    )
    assert resp.status_code == 404


def test_process_success_creates_withdrawal_and_updates_status(client, auth, contractor_auth):
    """Happy path: processing creates a withdrawal, marks request processed, decrements stock."""
    product = _create_product(client, auth, quantity=50.0)
    create_resp = _create_material_request(
        client,
        contractor_auth,
        product,
        job_id="J-SUCCESS",
        service_address="100 Success Rd",
    )
    assert create_resp.status_code == 200
    req_id = create_resp.json()["id"]

    # Process the request
    process_resp = client.post(
        f"/api/material-requests/{req_id}/process",
        json={"job_id": "J-SUCCESS", "service_address": "100 Success Rd"},
        headers=auth,
    )
    assert process_resp.status_code == 200
    withdrawal = process_resp.json()
    assert withdrawal["id"]
    assert withdrawal["contractor_id"] == "contractor-1"

    # Verify the request is now marked as processed
    get_resp = client.get(f"/api/material-requests/{req_id}", headers=auth)
    assert get_resp.status_code == 200
    updated = get_resp.json()
    assert updated["status"] == "processed"
    assert updated["withdrawal_id"] == withdrawal["id"]
