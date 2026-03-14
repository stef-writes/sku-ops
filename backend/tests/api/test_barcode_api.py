"""Tests for GET /api/catalog/skus/by-barcode structured error responses."""

import pytest

from catalog.application.sku_lifecycle import create_product_with_sku
from inventory.application.inventory_service import process_import_stock_changes


@pytest.mark.asyncio
async def test_by_barcode_found_returns_product(db, client, auth_headers):
    """Happy path: scanning a known barcode returns the product."""
    product = await create_product_with_sku(
        category_id="dept-1",
        category_name="Hardware",
        name="Test Pipe",
        barcode="042100005264",  # valid UPC-A
        user_id="user-1",
        user_name="Test",
        on_stock_import=process_import_stock_changes,
    )

    resp = client.get("/api/catalog/skus/by-barcode?barcode=042100005264", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == product.id
    assert data["barcode"] == "042100005264"


@pytest.mark.asyncio
async def test_by_barcode_not_found_returns_structured_error(db, client, auth_headers):
    """Scanning a barcode with no matching product returns 404 with code: not_found."""
    resp = client.get("/api/catalog/skus/by-barcode?barcode=HDW-ITM-999999", headers=auth_headers)
    assert resp.status_code == 404
    detail = resp.json()["detail"]
    assert detail["code"] == "not_found"
    assert detail["barcode"] == "HDW-ITM-999999"


@pytest.mark.asyncio
async def test_by_barcode_invalid_upc_check_digit_returns_structured_error(
    db, client, auth_headers
):
    """Scanning a 12-digit UPC with a wrong check digit returns 422 with code: invalid_check_digit."""
    # 042100005265 has a bad check digit (valid: 042100005264)
    resp = client.get("/api/catalog/skus/by-barcode?barcode=042100005265", headers=auth_headers)
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["code"] == "invalid_check_digit"
    assert detail["barcode"] == "042100005265"


@pytest.mark.asyncio
async def test_by_barcode_invalid_ean13_check_digit_returns_structured_error(
    db, client, auth_headers
):
    """Scanning a 13-digit EAN-13 with a wrong check digit returns 422 with code: invalid_check_digit."""
    # 5901234123458 has wrong check digit (valid: 5901234123457)
    resp = client.get("/api/catalog/skus/by-barcode?barcode=5901234123458", headers=auth_headers)
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["code"] == "invalid_check_digit"
    assert detail["barcode"] == "5901234123458"


def test_by_barcode_requires_auth(client):
    """Endpoint must reject unauthenticated requests."""
    resp = client.get("/api/catalog/skus/by-barcode?barcode=HDW-ITM-000001")
    assert resp.status_code in (401, 403)
