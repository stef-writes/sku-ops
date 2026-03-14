"""Withdrawal repository port — testable contract for withdrawal persistence."""

from typing import Protocol, runtime_checkable

from operations.domain.withdrawal import MaterialWithdrawal


@runtime_checkable
class WithdrawalRepoPort(Protocol):
    async def insert(self, withdrawal: MaterialWithdrawal) -> None: ...

    async def list_withdrawals(
        self,
        contractor_id: str | None = None,
        payment_status: str | None = None,
        billing_entity: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 10000,
        offset: int = 0,
    ) -> list[MaterialWithdrawal]: ...

    async def get_by_id(
        self,
        withdrawal_id: str,
    ) -> MaterialWithdrawal | None: ...

    async def mark_paid(
        self,
        withdrawal_id: str,
        paid_at: str,
    ) -> MaterialWithdrawal | None: ...

    async def bulk_mark_paid(
        self,
        withdrawal_ids: list[str],
        paid_at: str,
    ) -> list[str]: ...
