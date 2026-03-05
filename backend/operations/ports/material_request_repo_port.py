"""Material request repository port — testable contract for material request persistence."""
from typing import List, Optional, Protocol, runtime_checkable

from operations.domain.material_request import MaterialRequest


@runtime_checkable
class MaterialRequestRepoPort(Protocol):

    async def insert(self, request: MaterialRequest, conn=None) -> None: ...

    async def get_by_id(
        self, request_id: str, organization_id: Optional[str] = None,
    ) -> Optional[dict]: ...

    async def list_pending(
        self, organization_id: Optional[str] = None, limit: int = 100,
    ) -> List[dict]: ...

    async def list_by_contractor(
        self, contractor_id: str, organization_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[dict]: ...

    async def mark_processed(
        self, request_id: str, withdrawal_id: str, processed_by_id: str,
        processed_at: str, conn=None,
    ) -> bool: ...
