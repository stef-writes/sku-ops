"""Billing entity master data routes."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from identity.application.auth_service import get_current_user, require_role
from identity.domain.billing_entity import BillingEntity, BillingEntityCreate, BillingEntityUpdate
from identity.infrastructure.billing_entity_repo import billing_entity_repo
from kernel.types import CurrentUser

router = APIRouter(prefix="/billing-entities", tags=["billing-entities"])


@router.get("")
async def list_billing_entities(
    is_active: bool | None = None,
    q: str | None = None,
    limit: int = 200,
    offset: int = 0,
    current_user: CurrentUser = Depends(get_current_user),
):
    return await billing_entity_repo.list_billing_entities(
        organization_id=current_user.organization_id,
        is_active=is_active, q=q, limit=limit, offset=offset,
    )


@router.get("/search")
async def search_billing_entities(
    q: str = "",
    limit: int = 20,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Autocomplete endpoint for billing entity pickers."""
    if not q.strip():
        return await billing_entity_repo.list_billing_entities(
            organization_id=current_user.organization_id,
            is_active=True, limit=limit,
        )
    return await billing_entity_repo.search(q, current_user.organization_id, limit=limit)


@router.get("/{entity_id}")
async def get_billing_entity(entity_id: str, current_user: CurrentUser = Depends(get_current_user)):
    entity = await billing_entity_repo.get_by_id(entity_id, current_user.organization_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Billing entity not found")
    return entity


@router.post("")
async def create_billing_entity(
    data: BillingEntityCreate,
    current_user: CurrentUser = Depends(require_role("admin", "warehouse_manager")),
):
    org_id = current_user.organization_id
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")

    existing = await billing_entity_repo.get_by_name(name, org_id)
    if existing:
        raise HTTPException(status_code=409, detail=f"Billing entity '{name}' already exists")

    entity = BillingEntity(
        name=name,
        contact_name=data.contact_name,
        contact_email=data.contact_email,
        billing_address=data.billing_address,
        payment_terms=data.payment_terms,
        organization_id=org_id,
    )
    await billing_entity_repo.insert(entity)
    return entity.model_dump()


@router.put("/{entity_id}")
async def update_billing_entity(
    entity_id: str,
    data: BillingEntityUpdate,
    current_user: CurrentUser = Depends(require_role("admin", "warehouse_manager")),
):
    org_id = current_user.organization_id
    existing = await billing_entity_repo.get_by_id(entity_id, org_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Billing entity not found")

    updates = data.model_dump(exclude_none=True)
    result = await billing_entity_repo.update(entity_id, updates, org_id)
    return result
