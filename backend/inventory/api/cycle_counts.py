"""Cycle count routes — inventory bounded context."""

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from inventory.application.cycle_count_service import (
    commit_cycle_count,
    get_count_detail,
    list_cycle_counts,
    open_cycle_count,
    update_counted_qty,
)
from kernel.errors import ResourceNotFoundError
from kernel import events
from shared.api.deps import ManagerDep
from shared.infrastructure import event_hub
from shared.infrastructure.middleware.audit import audit_log

router = APIRouter(prefix="/cycle-counts", tags=["cycle-counts"])


class OpenCycleCountRequest(BaseModel):
    scope: str | None = None  # department name; omit for full-warehouse count


class UpdateItemRequest(BaseModel):
    counted_qty: float
    notes: str | None = None


@router.post("", status_code=201)
async def open_count(
    data: OpenCycleCountRequest,
    request: Request,
    current_user: ManagerDep,
):
    try:
        count = await open_cycle_count(
            organization_id=current_user.organization_id,
            created_by_id=current_user.id,
            created_by_name=current_user.name,
            scope=data.scope,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    await audit_log(
        user_id=current_user.id, action="cycle_count.open",
        resource_type="cycle_count", resource_id=count["id"],
        details={"scope": data.scope},
        request=request, org_id=current_user.organization_id,
    )
    return count


@router.get("")
async def list_counts(
    current_user: ManagerDep,
    status: str | None = Query(None, description="Filter by status: open or committed"),
):
    return await list_cycle_counts(
        organization_id=current_user.organization_id,
        status=status,
    )


@router.get("/{count_id}")
async def get_count(
    count_id: str,
    current_user: ManagerDep,
):
    try:
        return await get_count_detail(count_id, current_user.organization_id)
    except ResourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.patch("/{count_id}/items/{item_id}")
async def update_item(
    count_id: str,
    item_id: str,
    data: UpdateItemRequest,
    current_user: ManagerDep,
):
    try:
        return await update_counted_qty(
            count_id=count_id,
            item_id=item_id,
            counted_qty=data.counted_qty,
            notes=data.notes,
            organization_id=current_user.organization_id,
        )
    except ResourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/{count_id}/commit")
async def commit_count(
    count_id: str,
    request: Request,
    current_user: ManagerDep,
):
    try:
        result = await commit_cycle_count(
            count_id=count_id,
            organization_id=current_user.organization_id,
            committed_by_id=current_user.id,
            committed_by_name=current_user.name,
        )
    except ResourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    await audit_log(
        user_id=current_user.id, action="cycle_count.commit",
        resource_type="cycle_count", resource_id=count_id,
        details={"items_adjusted": result.get("items_adjusted", 0)},
        request=request, org_id=current_user.organization_id,
    )
    await event_hub.emit(events.INVENTORY_UPDATED, org_id=current_user.organization_id)
    return result
