"""Job master data routes."""

from fastapi import APIRouter, HTTPException

from jobs.application.queries import (
    get_job_by_code,
    get_job_by_id,
    insert_job,
)
from jobs.application.queries import (
    list_jobs as query_list_jobs,
)
from jobs.application.queries import (
    search_jobs as query_search_jobs,
)
from jobs.application.queries import (
    update_job as query_update_job,
)
from jobs.domain.job import Job, JobCreate, JobStatus, JobUpdate
from shared.api.deps import AdminDep, CurrentUserDep

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("")
async def list_jobs(
    current_user: AdminDep,
    status: str | None = None,
    q: str | None = None,
    limit: int = 200,
    offset: int = 0,
):
    return await query_list_jobs(
        status=status,
        q=q,
        limit=limit,
        offset=offset,
    )


@router.get("/search")
async def search_jobs(
    current_user: CurrentUserDep,
    q: str = "",
    limit: int = 20,
):
    """Autocomplete endpoint for job pickers (all authenticated users including contractors)."""
    if not q.strip():
        return await query_list_jobs(
            status="active",
            limit=limit,
        )
    return await query_search_jobs(q, limit=limit)


@router.get("/{job_id}")
async def get_job(job_id: str, current_user: CurrentUserDep):
    job = await get_job_by_id(job_id)
    if not job:
        job = await get_job_by_code(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("")
async def create_job(
    data: JobCreate,
    current_user: AdminDep,
):
    code = data.code.strip()
    if not code:
        raise HTTPException(status_code=400, detail="Job code is required")

    existing = await get_job_by_code(code)
    if existing:
        raise HTTPException(status_code=409, detail=f"Job with code '{code}' already exists")

    job = Job(
        code=code,
        name=data.name or code,
        service_address=data.service_address,
        notes=data.notes,
        organization_id=current_user.organization_id,
    )
    await insert_job(job)
    return job.model_dump()


@router.put("/{job_id}")
async def update_job(
    job_id: str,
    data: JobUpdate,
    current_user: AdminDep,
):
    existing = await get_job_by_id(job_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Job not found")

    updates = data.model_dump(exclude_none=True)
    if "status" in updates:
        valid = {s.value for s in JobStatus}
        if updates["status"] not in valid:
            raise HTTPException(
                status_code=400, detail=f"Invalid status. Must be one of: {', '.join(valid)}"
            )

    result = await query_update_job(job_id, updates)
    return result
