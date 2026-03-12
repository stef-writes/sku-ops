"""Operations application queries — safe for cross-context import.

Other bounded contexts import from here, never from operations.infrastructure directly.
Thin delegation layer that decouples consumers from infrastructure details.
"""

from operations.domain.material_request import MaterialRequest
from operations.domain.returns import MaterialReturn
from operations.domain.withdrawal import MaterialWithdrawal
from operations.infrastructure.material_request_repo import material_request_repo as _mr_repo
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
) -> list[MaterialWithdrawal]:
    return await _wd_repo.list_withdrawals(
        contractor_id=contractor_id,
        payment_status=payment_status,
        billing_entity=billing_entity,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )


async def get_withdrawal_by_id(
    withdrawal_id: str,
) -> MaterialWithdrawal | None:
    return await _wd_repo.get_by_id(withdrawal_id)


async def mark_withdrawal_paid(withdrawal_id: str, paid_at: str) -> MaterialWithdrawal | None:
    return await _wd_repo.mark_paid(withdrawal_id, paid_at)


async def list_returns(
    contractor_id: str | None = None,
    withdrawal_id: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 500,
) -> list[MaterialReturn]:
    return await _ret_repo.list_returns(
        contractor_id=contractor_id,
        withdrawal_id=withdrawal_id,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )


async def get_return_by_id(
    return_id: str,
) -> MaterialReturn | None:
    return await _ret_repo.get_by_id(return_id)


async def link_withdrawal_to_invoice(withdrawal_id: str, invoice_id: str) -> None:
    """Link a withdrawal to an invoice. Operations owns this mutation."""
    await _wd_repo.link_to_invoice(withdrawal_id, invoice_id)


async def unlink_withdrawals_from_invoice(withdrawal_ids: list[str]) -> None:
    """Unlink withdrawals from invoice and reset to unpaid."""
    await _wd_repo.unlink_from_invoice(withdrawal_ids)


async def mark_withdrawals_paid_by_invoice(invoice_id: str, paid_at: str) -> None:
    """Mark all withdrawals linked to an invoice as paid."""
    await _wd_repo.mark_paid_by_invoice(invoice_id, paid_at)


async def link_credit_note_to_return(return_id: str, credit_note_id: str) -> None:
    """Set credit_note_id on a return. Operations owns this mutation."""
    await _ret_repo.link_credit_note(return_id, credit_note_id)


async def units_sold_by_product(
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, float]:
    return await _wd_repo.units_sold_by_product(start_date, end_date)


async def payment_status_breakdown(
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, float]:
    return await _wd_repo.payment_status_breakdown(start_date, end_date)


# --- Material request re-exports ---


async def insert_material_request(request: MaterialRequest | dict) -> None:
    return await _mr_repo.insert(request)


async def get_material_request_by_id(
    request_id: str,
) -> MaterialRequest | None:
    return await _mr_repo.get_by_id(request_id)


async def list_material_requests_by_contractor(
    contractor_id: str,
    limit: int = 100,
) -> list[MaterialRequest]:
    return await _mr_repo.list_by_contractor(
        contractor_id=contractor_id,
        limit=limit,
    )


async def list_pending_material_requests(
    limit: int = 100,
) -> list[MaterialRequest]:
    return await _mr_repo.list_pending(
        limit=limit,
    )


async def mark_material_request_processed(
    request_id: str,
    withdrawal_id: str,
    processed_by_id: str,
    processed_at: str,
) -> bool:
    return await _mr_repo.mark_processed(
        request_id=request_id,
        withdrawal_id=withdrawal_id,
        processed_by_id=processed_by_id,
        processed_at=processed_at,
    )
