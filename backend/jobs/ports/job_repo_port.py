"""Job repository port — testable contract for job persistence."""
from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class JobRepoPort(Protocol):

    async def insert(self, job, conn=None) -> None: ...

    async def get_by_id(self, job_id: str, organization_id: str) -> Optional[dict]: ...

    async def get_by_code(self, code: str, organization_id: str) -> Optional[dict]: ...

    async def list_jobs(
        self,
        organization_id: str,
        status: Optional[str] = None,
        q: Optional[str] = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list: ...

    async def update(self, job_id: str, updates: dict, organization_id: str) -> Optional[dict]: ...

    async def search(self, query: str, organization_id: str, limit: int = 20) -> list: ...

    async def ensure_job(self, code: str, organization_id: str, conn=None) -> dict: ...
