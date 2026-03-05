"""Withdrawal repository port — testable contract for withdrawal persistence."""
from typing import List, Optional, Protocol, runtime_checkable

from operations.domain.withdrawal import MaterialWithdrawal


@runtime_checkable
class WithdrawalRepoPort(Protocol):

    async def insert(self, withdrawal: MaterialWithdrawal, conn=None) -> None: ...

    async def list_withdrawals(
        self,
        contractor_id: Optional[str] = None,
        payment_status: Optional[str] = None,
        billing_entity: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 10000,
        offset: int = 0,
        organization_id: Optional[str] = None,
    ) -> List[dict]: ...

    async def get_by_id(
        self, withdrawal_id: str, organization_id: Optional[str] = None,
    ) -> Optional[dict]: ...

    async def mark_paid(
        self, withdrawal_id: str, paid_at: str,
    ) -> Optional[dict]: ...

    async def bulk_mark_paid(
        self, withdrawal_ids: List[str], paid_at: str,
        organization_id: Optional[str] = None,
    ) -> int: ...
