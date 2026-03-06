"""Address book routes — CRUD and autocomplete for saved addresses."""
from datetime import UTC, datetime, timezone
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from identity.application.auth_service import get_current_user, require_role
from identity.infrastructure.address_repo import address_repo
from kernel.types import CurrentUser

router = APIRouter(prefix="/addresses", tags=["addresses"])


class AddressCreate(BaseModel):
    label: str = ""
    line1: str
    line2: str = ""
    city: str = ""
    state: str = ""
    postal_code: str = ""
    country: str = "US"
    billing_entity_id: str | None = None
    job_id: str | None = None


@router.get("")
async def list_addresses(
    billing_entity_id: str | None = None,
    job_id: str | None = None,
    q: str | None = None,
    limit: int = 100,
    offset: int = 0,
    current_user: CurrentUser = Depends(require_role("admin", "warehouse_manager")),
):
    return await address_repo.list_addresses(
        organization_id=current_user.organization_id,
        billing_entity_id=billing_entity_id, job_id=job_id,
        q=q, limit=limit, offset=offset,
    )


@router.get("/search")
async def search_addresses(
    q: str = "",
    limit: int = 20,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Autocomplete endpoint for address pickers."""
    if not q.strip():
        return await address_repo.list_addresses(
            organization_id=current_user.organization_id, limit=limit,
        )
    return await address_repo.search(q, current_user.organization_id, limit=limit)


@router.get("/{address_id}")
async def get_address(address_id: str, current_user: CurrentUser = Depends(require_role("admin", "warehouse_manager"))):
    addr = await address_repo.get_by_id(address_id, current_user.organization_id)
    if not addr:
        raise HTTPException(status_code=404, detail="Address not found")
    return addr


@router.post("")
async def create_address(
    data: AddressCreate,
    current_user: CurrentUser = Depends(require_role("admin", "warehouse_manager")),
):
    if not data.line1.strip():
        raise HTTPException(status_code=400, detail="Address line 1 is required")

    address = {
        "id": str(uuid4()),
        "label": data.label or data.line1[:80],
        "line1": data.line1,
        "line2": data.line2,
        "city": data.city,
        "state": data.state,
        "postal_code": data.postal_code,
        "country": data.country,
        "billing_entity_id": data.billing_entity_id,
        "job_id": data.job_id,
        "organization_id": current_user.organization_id,
        "created_at": datetime.now(UTC).isoformat(),
    }
    await address_repo.insert(address)
    return address
