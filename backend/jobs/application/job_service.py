"""Job application service — safe for cross-context import.

Other bounded contexts import from here, never from jobs.infrastructure directly.
"""
from jobs.infrastructure.job_repo import job_repo


async def ensure_job(code: str, organization_id: str, conn=None) -> dict:
    """Get existing job by code, or auto-create a minimal one."""
    return await job_repo.ensure_job(code, organization_id, conn=conn)
