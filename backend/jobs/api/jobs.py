"""Job master data routes."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from identity.application.auth_service import get_current_user, require_role
from jobs.domain.job import JobCreate, JobStatus, JobUpdate
from jobs.infrastructure.job_repo import job_repo
from kernel.types import CurrentUser

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("")
async def list_jobs(
    status: str | None = None,
    q: str | None = None,
    limit: int = 200,
    offset: int = 0,
    current_user: CurrentUser = Depends(require_role("admin", "warehouse_manager")),
):
    return await job_repo.list_jobs(
        organization_id=current_user.organization_id,
        status=status, q=q, limit=limit, offset=offset,
    )


@router.get("/search")
async def search_jobs(
    q: str = "",
    limit: int = 20,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Autocomplete endpoint for job pickers (all authenticated users including contractors)."""
    if not q.strip():
        return await job_repo.list_jobs(
            organization_id=current_user.organization_id,
            status="active", limit=limit,
        )
    return await job_repo.search(q, current_user.organization_id, limit=limit)


@router.get("/{job_id}")
async def get_job(job_id: str, current_user: CurrentUser = Depends(get_current_user)):
    org_id = current_user.organization_id
    job = await job_repo.get_by_id(job_id, org_id)
    if not job:
        job = await job_repo.get_by_code(job_id, org_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("")
async def create_job(
    data: JobCreate,
    current_user: CurrentUser = Depends(require_role("admin", "warehouse_manager")),
):
    org_id = current_user.organization_id
    code = data.code.strip()
    if not code:
        raise HTTPException(status_code=400, detail="Job code is required")

    existing = await job_repo.get_by_code(code, org_id)
    if existing:
        raise HTTPException(status_code=409, detail=f"Job with code '{code}' already exists")

    from jobs.domain.job import Job
    job = Job(
        code=code,
        name=data.name or code,
        service_address=data.service_address,
        notes=data.notes,
        organization_id=org_id,
    )
    await job_repo.insert(job)
    return job.model_dump()


@router.put("/{job_id}")
async def update_job(
    job_id: str,
    data: JobUpdate,
    current_user: CurrentUser = Depends(require_role("admin", "warehouse_manager")),
):
    org_id = current_user.organization_id
    existing = await job_repo.get_by_id(job_id, org_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Job not found")

    updates = data.model_dump(exclude_none=True)
    if "status" in updates:
        valid = {s.value for s in JobStatus}
        if updates["status"] not in valid:
            raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {', '.join(valid)}")

    result = await job_repo.update(job_id, updates, org_id)
    return result
