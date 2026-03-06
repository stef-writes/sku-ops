"""Tests for material request creation and processing with fallback logic."""
import pytest
from fastapi import HTTPException

from catalog.application.product_lifecycle import create_product
from inventory.application.inventory_service import process_import_stock_changes
from kernel.types import CurrentUser
from operations.api.material_requests import (
    create_material_request,
    list_material_requests,
    process_material_request,
)
from operations.domain.material_request import (
    MaterialRequest,
    MaterialRequestCreate,
    MaterialRequestProcess,
)
from operations.domain.withdrawal import WithdrawalItem
from operations.infrastructure.material_request_repo import material_request_repo


def _admin():
    return CurrentUser(id="user-1", email="test@test.com", name="Test User", role="admin")


def _contractor():
    return CurrentUser(id="contractor-1", email="contractor@test.com", name="Contractor User", role="contractor")


async def _create_test_product(name="Widget", quantity=100.0, cost=5.0, price=10.0):
    return await create_product(
        department_id="dept-1", department_name="Hardware",
        name=name, quantity=quantity, price=price, cost=cost,
        user_id="user-1", user_name="Test",
        on_stock_import=process_import_stock_changes,
    )


def _item_from_product(product, quantity=3):
    return WithdrawalItem(
        product_id=product.id, sku=product.sku,
        name=product.name, quantity=quantity,
        price=10.0, cost=5.0, subtotal=round(10.0 * quantity, 2),
    )


async def _create_request_in_db(product, job_id="JOB-001", service_address="123 Main St"):
    """Insert a material request directly into the DB (bypassing API layer)."""
    req = MaterialRequest(
        contractor_id="contractor-1",
        contractor_name="Contractor User",
        items=[WithdrawalItem(
            product_id=product.id, sku=product.sku,
            name=product.name, quantity=3,
            price=10.0, cost=5.0, subtotal=30.0,
        )],
        job_id=job_id,
        service_address=service_address,
        notes="Test request",
    )
    await material_request_repo.insert(req)
    return req


@pytest.mark.asyncio
async def test_material_request_create_model_validation(db):
    """MaterialRequestCreate requires items; job_id/service_address/notes are optional."""
    product = await _create_test_product()
    item = WithdrawalItem(
        product_id=product.id, sku=product.sku,
        name=product.name, quantity=2,
        price=10.0, cost=5.0, subtotal=20.0,
    )

    minimal = MaterialRequestCreate(items=[item])
    assert len(minimal.items) == 1
    assert minimal.job_id is None
    assert minimal.service_address is None
    assert minimal.notes is None

    full = MaterialRequestCreate(
        items=[item], job_id="J-100",
        service_address="789 Pine", notes="Urgent",
    )
    assert full.job_id == "J-100"
    assert full.service_address == "789 Pine"
    assert full.notes == "Urgent"

    with pytest.raises(Exception):
        MaterialRequestCreate()


@pytest.mark.asyncio
async def test_material_request_process_model_allows_empty(db):
    """MaterialRequestProcess should accept empty job_id and service_address."""
    model = MaterialRequestProcess()
    assert model.job_id is None
    assert model.service_address is None

    model_with = MaterialRequestProcess(job_id="J-1", service_address="123 Oak")
    assert model_with.job_id == "J-1"


@pytest.mark.asyncio
async def test_material_request_round_trip(db):
    """Material request persisted and retrieved with correct fields."""
    product = await _create_test_product()
    req = await _create_request_in_db(product)

    fetched = await material_request_repo.get_by_id(req.id)
    assert fetched is not None
    assert fetched["contractor_id"] == "contractor-1"
    assert fetched["job_id"] == "JOB-001"
    assert fetched["service_address"] == "123 Main St"
    assert fetched["status"] == "pending"
    assert len(fetched["items"]) == 1


@pytest.mark.asyncio
async def test_material_request_fallback_fields_preserved(db):
    """When contractor supplies job_id and service_address, they're stored in the request."""
    product = await _create_test_product()
    req = await _create_request_in_db(product, job_id="FALLBACK-JOB", service_address="456 Elm")

    fetched = await material_request_repo.get_by_id(req.id)
    assert fetched["job_id"] == "FALLBACK-JOB"
    assert fetched["service_address"] == "456 Elm"


# ── API handler: create ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_material_request_as_contractor(db):
    """Contractor can create a material request via the API handler."""
    product = await _create_test_product()
    data = MaterialRequestCreate(
        items=[_item_from_product(product)],
        job_id="JOB-200", service_address="100 Main St",
    )

    result = await create_material_request(data=data, current_user=_contractor())

    assert result["contractor_id"] == "contractor-1"
    assert result["contractor_name"] == "Contractor User"
    assert result["job_id"] == "JOB-200"
    assert result["service_address"] == "100 Main St"
    assert result["status"] == "pending"
    assert len(result["items"]) == 1


@pytest.mark.asyncio
async def test_create_material_request_rejects_non_contractor(db):
    """Admin/staff cannot create material requests — only contractors."""
    product = await _create_test_product()
    data = MaterialRequestCreate(items=[_item_from_product(product)])

    with pytest.raises(HTTPException) as exc:
        await create_material_request(data=data, current_user=_admin())
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_create_material_request_rejects_empty_items(db):
    """Request with no items is rejected."""
    data = MaterialRequestCreate(items=[])

    with pytest.raises(HTTPException) as exc:
        await create_material_request(data=data, current_user=_contractor())
    assert exc.value.status_code == 400
    assert "item" in exc.value.detail.lower()


# ── API handler: list ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_material_requests_contractor_sees_own(db):
    """Contractor only sees their own requests."""
    product = await _create_test_product()
    await _create_request_in_db(product)

    results = await list_material_requests(current_user=_contractor())

    assert len(results) >= 1
    assert all(r["contractor_id"] == "contractor-1" for r in results)


@pytest.mark.asyncio
async def test_list_material_requests_admin_sees_pending(db):
    """Admin sees all pending requests."""
    product = await _create_test_product()
    await _create_request_in_db(product)

    results = await list_material_requests(current_user=_admin())

    assert len(results) >= 1
    assert all(r["status"] == "pending" for r in results)


# ── API handler: process validation ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_process_rejects_already_processed(db):
    """Cannot process a request that's already been processed."""
    product = await _create_test_product()
    req = await _create_request_in_db(product, job_id="J-1", service_address="1 Elm")

    await material_request_repo.mark_processed(
        request_id=req.id, withdrawal_id="w-fake",
        processed_by_id="user-1", processed_at="2025-01-01T00:00:00Z",
    )

    with pytest.raises(HTTPException) as exc:
        await process_material_request(
            request_id=req.id,
            data=MaterialRequestProcess(job_id="J-1", service_address="1 Elm"),
            current_user=_admin(),
        )
    assert exc.value.status_code == 400
    assert "already processed" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_process_rejects_missing_job_id(db):
    """Processing requires a job_id (from staff or contractor fallback)."""
    product = await _create_test_product()
    req = await _create_request_in_db(product, job_id="", service_address="1 Oak")

    with pytest.raises(HTTPException) as exc:
        await process_material_request(
            request_id=req.id,
            data=MaterialRequestProcess(service_address="1 Oak"),
            current_user=_admin(),
        )
    assert exc.value.status_code == 400
    assert "job id" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_process_rejects_missing_service_address(db):
    """Processing requires a service_address (from staff or contractor fallback)."""
    product = await _create_test_product()
    req = await _create_request_in_db(product, job_id="J-1", service_address="")

    with pytest.raises(HTTPException) as exc:
        await process_material_request(
            request_id=req.id,
            data=MaterialRequestProcess(job_id="J-1"),
            current_user=_admin(),
        )
    assert exc.value.status_code == 400
    assert "service address" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_process_not_found(db):
    """Processing a non-existent request returns 404."""
    with pytest.raises(HTTPException) as exc:
        await process_material_request(
            request_id="nonexistent-id",
            data=MaterialRequestProcess(job_id="J-1", service_address="1 Elm"),
            current_user=_admin(),
        )
    assert exc.value.status_code == 404
