"""Return repository port."""
from typing import Any, Optional, Protocol


class ReturnRepoPort(Protocol):
    async def insert(self, ret: Any, conn: Any = None) -> None: ...
    async def get_by_id(self, return_id: str, organization_id: Optional[str] = None) -> Optional[dict]: ...
    async def list_returns(
        self,
        contractor_id: Optional[str] = None,
        withdrawal_id: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 500,
        organization_id: Optional[str] = None,
    ) -> list: ...
    async def list_by_withdrawal(self, withdrawal_id: str) -> list: ...
