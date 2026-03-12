"""Job application queries — safe for cross-context import.

API and other bounded contexts import from here, never from jobs.infrastructure directly.
Thin delegation layer that decouples consumers from infrastructure details.
"""

from jobs.domain.job import Job
from jobs.infrastructure.job_repo import job_repo as _job_repo


async def list_jobs(
    status: str | None = None,
    q: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[Job]:
    return await _job_repo.list_jobs(
        status=status,
        q=q,
        limit=limit,
        offset=offset,
    )


async def search_jobs(query: str, limit: int = 20) -> list[Job]:
    return await _job_repo.search(query, limit=limit)


async def get_job_by_id(job_id: str) -> Job | None:
    return await _job_repo.get_by_id(job_id)


async def get_job_by_code(code: str) -> Job | None:
    return await _job_repo.get_by_code(code)


async def insert_job(job: Job | dict) -> None:
    return await _job_repo.insert(job)


async def update_job(job_id: str, updates: dict) -> Job | None:
    return await _job_repo.update(job_id, updates)
