"""Return service: validate against original withdrawal, restock, create credit note."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from finance.application.ledger_service import record_return as _record_ledger
from inventory.domain.stock import StockTransactionType
from kernel.errors import DomainError, ResourceNotFoundError
from operations.domain.returns import MaterialReturn, ReturnCreate, ReturnItem
from operations.infrastructure.return_repo import return_repo as _default_return_repo
from shared.infrastructure.database import transaction

if TYPE_CHECKING:
    from kernel.types import CurrentUser
    from operations.ports.return_repo_port import ReturnRepoPort

GetWithdrawalFn = Callable[..., Awaitable[dict | None]]
RestockFn = Callable[..., Awaitable[None]]
CreateCreditNoteFn = Callable[..., Awaitable[dict]] | None


async def create_return(
    data: ReturnCreate,
    current_user: CurrentUser,
    *,
    get_withdrawal: GetWithdrawalFn,
    restock: RestockFn,
    create_credit_note: CreateCreditNoteFn = None,
    return_repo: ReturnRepoPort = _default_return_repo,
    tax_rate: float = 0.10,
) -> dict:
    """Process a return against a previous withdrawal.

    1. Validates every returned item against the original withdrawal
    2. Restocks inventory (RETURN transaction type)
    3. Creates a credit note if an invoice exists
    """
    org_id = current_user.organization_id
    withdrawal = await get_withdrawal(data.withdrawal_id, organization_id=org_id)
    if not withdrawal:
        raise ResourceNotFoundError("Withdrawal", data.withdrawal_id)

    w_items = withdrawal.get("items", [])
    w_item_map: dict[str, dict] = {}
    for wi in w_items:
        pid = wi.get("product_id", "")
        if pid not in w_item_map:
            w_item_map[pid] = wi
        else:
            w_item_map[pid] = {
                **wi,
                "quantity": w_item_map[pid].get("quantity", 0) + wi.get("quantity", 0),
            }

    existing_returns = await return_repo.list_by_withdrawal(data.withdrawal_id)
    already_returned: dict[str, float] = {}
    for er in existing_returns:
        for ri in er.get("items", []):
            pid = ri.get("product_id", "")
            already_returned[pid] = already_returned.get(pid, 0) + ri.get("quantity", 0)

    enriched_items: list[ReturnItem] = []
    for item in data.items:
        original = w_item_map.get(item.product_id)
        if not original:
            raise DomainError(f"Product {item.product_id} ({item.sku}) not on original withdrawal")

        max_returnable = original.get("quantity", 0) - already_returned.get(item.product_id, 0)
        if item.quantity > max_returnable:
            raise DomainError(
                f"Cannot return {item.quantity} of {item.name} — max returnable is {max_returnable}"
            )

        enriched = item.model_copy(
            update={
                "unit_price": item.unit_price
                or (original.get("unit_price") or original.get("price") or 0),
                "cost": item.cost or original.get("cost", 0),
                "unit": item.unit or original.get("unit", "each"),
            }
        )
        enriched_items.append(enriched)

    ret = MaterialReturn(
        withdrawal_id=data.withdrawal_id,
        contractor_id=withdrawal.get("contractor_id", ""),
        contractor_name=withdrawal.get("contractor_name", ""),
        billing_entity=withdrawal.get("billing_entity", ""),
        job_id=withdrawal.get("job_id", ""),
        items=enriched_items,
        reason=data.reason,
        notes=data.notes,
        processed_by_id=current_user.id,
        processed_by_name=current_user.name,
    )
    ret.compute_totals(tax_rate=tax_rate)
    ret.organization_id = org_id

    async def _do_return(conn):
        for item in enriched_items:
            await restock(
                product_id=item.product_id,
                sku=item.sku,
                product_name=item.name,
                quantity=item.quantity,
                user_id=current_user.id,
                user_name=current_user.name,
                reference_id=ret.id,
                unit=item.unit,
                organization_id=org_id,
                conn=conn,
                transaction_type=StockTransactionType.RETURN,
            )

        await return_repo.insert(ret, conn=conn)

        w_dept_map = {wi.get("product_id"): wi.get("department_name") for wi in w_items}
        ledger_items = [
            {
                "product_id": item.product_id,
                "quantity": item.quantity,
                "unit_price": item.unit_price,
                "cost": item.cost,
                "department_name": w_dept_map.get(item.product_id),
            }
            for item in enriched_items
        ]
        await _record_ledger(
            return_id=ret.id,
            items=ledger_items,
            tax=ret.tax,
            total=ret.total,
            job_id=ret.job_id,
            billing_entity=ret.billing_entity,
            contractor_id=ret.contractor_id,
            organization_id=org_id,
            performed_by_user_id=current_user.id,
            conn=conn,
        )

        result = ret.model_dump()

        if create_credit_note and withdrawal.get("invoice_id"):
            _log = logging.getLogger(__name__)
            try:
                cn = await create_credit_note(
                    return_id=ret.id,
                    invoice_id=withdrawal["invoice_id"],
                    items=enriched_items,
                    subtotal=ret.subtotal,
                    tax=ret.tax,
                    total=ret.total,
                    organization_id=org_id,
                    conn=conn,
                )
                result["credit_note_id"] = cn.get("id")

                from finance.application.credit_note_service import apply_credit_note as _apply_cn

                try:
                    await _apply_cn(
                        credit_note_id=cn["id"],
                        organization_id=org_id,
                        performed_by_user_id=current_user.id,
                    )
                except Exception:
                    _log.warning(
                        "Auto-apply credit note %s failed, credit note still created",
                        cn.get("id"),
                        exc_info=True,
                    )
            except (ValueError, RuntimeError, OSError):
                _log.warning(
                    "Credit note creation failed for return %s, continuing without credit note",
                    ret.id,
                    exc_info=True,
                )

        return result

    async with transaction() as conn:
        return await _do_return(conn)
