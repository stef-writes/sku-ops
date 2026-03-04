"""Operations application queries — safe for cross-context import.

Other bounded contexts import from here, never from operations.infrastructure directly.
Thin delegation layer that decouples consumers from infrastructure details.
"""
from typing import Optional

from operations.infrastructure.withdrawal_repo import withdrawal_repo as _repo


async def list_withdrawals(
    contractor_id: Optional[str] = None,
    payment_status: Optional[str] = None,
    billing_entity: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 10000,
    offset: int = 0,
    organization_id: Optional[str] = None,
) -> list:
    return await _repo.list_withdrawals(
        contractor_id=contractor_id, payment_status=payment_status,
        billing_entity=billing_entity, start_date=start_date,
        end_date=end_date, limit=limit, offset=offset,
        organization_id=organization_id,
    )


async def get_withdrawal_by_id(withdrawal_id: str, organization_id: Optional[str] = None) -> Optional[dict]:
    return await _repo.get_by_id(withdrawal_id, organization_id=organization_id)


async def mark_withdrawal_paid(withdrawal_id: str, paid_at: str, stripe_session_id: Optional[str] = None) -> Optional[dict]:
    return await _repo.mark_paid(withdrawal_id, paid_at, stripe_session_id=stripe_session_id)
