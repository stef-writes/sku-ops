"""Billing entity master data routes."""

from fastapi import APIRouter, HTTPException

from finance.application.billing_entity_service import (
    create_billing_entity as svc_create,
)
from finance.application.billing_entity_service import (
    get_by_name,
)
from finance.application.billing_entity_service import (
    update_billing_entity as svc_update,
)
from finance.application.queries import (
    get_billing_entity_by_id,
)
from finance.application.queries import (
    list_billing_entities as query_list,
)
from finance.application.queries import (
    search_billing_entities as query_search,
)
from finance.domain.billing_entity import BillingEntity, BillingEntityCreate, BillingEntityUpdate
from shared.api.deps import AdminDep

router = APIRouter(prefix="/billing-entities", tags=["billing-entities"])


@router.get("")
async def list_billing_entities(
    current_user: AdminDep,
    is_active: bool | None = None,
    q: str | None = None,
    limit: int = 200,
    offset: int = 0,
):
    return await query_list(
        organization_id=current_user.organization_id,
        is_active=is_active,
        q=q,
        limit=limit,
        offset=offset,
    )


@router.get("/search")
async def search_billing_entities(
    current_user: AdminDep,
    q: str = "",
    limit: int = 20,
):
    """Autocomplete endpoint for billing entity pickers."""
    if not q.strip():
        return await query_list(
            organization_id=current_user.organization_id,
            is_active=True,
            limit=limit,
        )
    return await query_search(q, current_user.organization_id, limit=limit)


@router.get("/{entity_id}")
async def get_billing_entity(entity_id: str, current_user: AdminDep):
    entity = await get_billing_entity_by_id(entity_id, current_user.organization_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Billing entity not found")
    return entity


@router.post("")
async def create_billing_entity(
    data: BillingEntityCreate,
    current_user: AdminDep,
):
    org_id = current_user.organization_id
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")

    existing = await get_by_name(name, org_id)
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
    await svc_create(entity)
    return entity.model_dump()


@router.put("/{entity_id}")
async def update_billing_entity(
    entity_id: str,
    data: BillingEntityUpdate,
    current_user: AdminDep,
):
    org_id = current_user.organization_id
    existing = await get_billing_entity_by_id(entity_id, org_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Billing entity not found")

    updates = data.model_dump(exclude_none=True)
    return await svc_update(entity_id, updates, org_id)
