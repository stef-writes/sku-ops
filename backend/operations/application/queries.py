"""Operations application queries — safe for cross-context import.

Other bounded contexts import from here, never from operations.infrastructure directly.
Thin delegation layer that decouples consumers from infrastructure details.
"""
from typing import Optional

from operations.infrastructure.return_repo import return_repo as _ret_repo
from operations.infrastructure.withdrawal_repo import withdrawal_repo as _wd_repo


async def list_withdrawals(
    contractor_id: str | None = None,
    payment_status: str | None = None,
    billing_entity: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 10000,
    offset: int = 0,
    organization_id: str | None = None,
) -> list:
    return await _wd_repo.list_withdrawals(
        contractor_id=contractor_id, payment_status=payment_status,
        billing_entity=billing_entity, start_date=start_date,
        end_date=end_date, limit=limit, offset=offset,
        organization_id=organization_id,
    )


async def get_withdrawal_by_id(withdrawal_id: str, organization_id: str | None = None) -> dict | None:
    return await _wd_repo.get_by_id(withdrawal_id, organization_id=organization_id)


async def mark_withdrawal_paid(withdrawal_id: str, paid_at: str) -> dict | None:
    return await _wd_repo.mark_paid(withdrawal_id, paid_at)


async def list_returns(
    contractor_id: str | None = None,
    withdrawal_id: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 500,
    organization_id: str | None = None,
) -> list:
    return await _ret_repo.list_returns(
        contractor_id=contractor_id, withdrawal_id=withdrawal_id,
        start_date=start_date, end_date=end_date,
        limit=limit, organization_id=organization_id,
    )


async def get_return_by_id(return_id: str, organization_id: str | None = None) -> dict | None:
    return await _ret_repo.get_by_id(return_id, organization_id=organization_id)
