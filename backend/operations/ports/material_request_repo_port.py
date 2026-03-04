"""Material request repository port — testable contract for material request persistence."""
from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class MaterialRequestRepoPort(Protocol):

    async def insert(self, request_dict: dict, conn=None) -> None: ...

    async def get_by_id(
        self, request_id: str, organization_id: Optional[str] = None,
    ) -> Optional[dict]: ...

    async def list_pending(
        self, organization_id: Optional[str] = None, limit: int = 100,
    ) -> list: ...

    async def list_by_contractor(
        self, contractor_id: str, organization_id: Optional[str] = None,
        limit: int = 100,
    ) -> list: ...

    async def mark_processed(
        self, request_id: str, withdrawal_id: str, processed_by_id: str,
        processed_at: str, conn=None,
    ) -> bool: ...
