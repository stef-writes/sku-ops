"""Address book routes — CRUD and autocomplete for saved addresses."""

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from identity.application.queries import address_repo
from shared.api.deps import AdminDep, CurrentUserDep

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
    current_user: AdminDep,
    billing_entity_id: str | None = None,
    job_id: str | None = None,
    q: str | None = None,
    limit: int = 100,
    offset: int = 0,
):
    return await address_repo.list_addresses(
        billing_entity_id=billing_entity_id,
        job_id=job_id,
        q=q,
        limit=limit,
        offset=offset,
    )


@router.get("/search")
async def search_addresses(
    current_user: CurrentUserDep,
    q: str = "",
    limit: int = 20,
):
    """Autocomplete endpoint for address pickers."""
    if not q.strip():
        return await address_repo.list_addresses(
            limit=limit,
        )
    return await address_repo.search(q, limit=limit)


@router.get("/{address_id}")
async def get_address(address_id: str, current_user: AdminDep):
    addr = await address_repo.get_by_id(address_id)
    if not addr:
        raise HTTPException(status_code=404, detail="Address not found")
    return addr


@router.post("")
async def create_address(
    data: AddressCreate,
    current_user: AdminDep,
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
