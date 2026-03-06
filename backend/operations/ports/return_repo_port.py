"""Return repository port."""
from typing import Any, Optional, Protocol


class ReturnRepoPort(Protocol):
    async def insert(self, ret: Any, conn: Any = None) -> None: ...
    async def get_by_id(self, return_id: str, organization_id: str | None = None) -> dict | None: ...
    async def list_returns(
        self,
        contractor_id: str | None = None,
        withdrawal_id: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 500,
        organization_id: str | None = None,
    ) -> list: ...
    async def list_by_withdrawal(self, withdrawal_id: str) -> list: ...
