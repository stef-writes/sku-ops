"""Return service: validate against original withdrawal, restock, create credit note."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from finance.application.credit_note_service import apply_credit_note as _apply_cn
from finance.application.credit_note_service import insert_credit_note
from finance.application.ledger_service import record_return as _record_ledger
from finance.application.org_settings_service import get_org_settings
from inventory.application import StockTransactionType
from inventory.application.inventory_service import restock_as_return
from operations.application.queries import get_withdrawal_by_id
from operations.domain.returns import MaterialReturn, ReturnCreate, ReturnItem
from operations.infrastructure.return_repo import return_repo as _default_return_repo
from shared.infrastructure.database import get_org_id, transaction
from shared.kernel.errors import DomainError, ResourceNotFoundError

if TYPE_CHECKING:
    from operations.ports.return_repo_port import ReturnRepoPort
    from shared.kernel.types import CurrentUser


async def create_return(
    data: ReturnCreate,
    current_user: CurrentUser,
    *,
    return_repo: ReturnRepoPort = _default_return_repo,
) -> dict:
    """Process a return against a previous withdrawal.

    1. Validates every returned item against the original withdrawal
    2. Restocks inventory (RETURN transaction type)
    3. Creates a credit note if an invoice exists
    """
    org_id = get_org_id()
    settings = await get_org_settings()
    tax_rate = settings.default_tax_rate

    withdrawal = await get_withdrawal_by_id(data.withdrawal_id)
    if not withdrawal:
        raise ResourceNotFoundError("Withdrawal", data.withdrawal_id)

    w_item_map: dict[str, object] = {}
    for wi in withdrawal.items:
        if wi.product_id not in w_item_map:
            w_item_map[wi.product_id] = wi
        else:
            prev = w_item_map[wi.product_id]
            w_item_map[wi.product_id] = wi.model_copy(
                update={"quantity": prev.quantity + wi.quantity}
            )

    existing_returns = await return_repo.list_by_withdrawal(data.withdrawal_id)
    already_returned: dict[str, float] = {}
    for er in existing_returns:
        for ri in er.items:
            already_returned[ri.product_id] = already_returned.get(ri.product_id, 0) + ri.quantity

    enriched_items: list[ReturnItem] = []
    for item in data.items:
        original = w_item_map.get(item.product_id)
        if not original:
            raise DomainError(f"Product {item.product_id} ({item.sku}) not on original withdrawal")

        max_returnable = original.quantity - already_returned.get(item.product_id, 0)
        if item.quantity > max_returnable:
            raise DomainError(
                f"Cannot return {item.quantity} of {item.name} — max returnable is {max_returnable}"
            )

        enriched = item.model_copy(
            update={
                "unit_price": item.unit_price or original.unit_price,
                "cost": item.cost or original.cost,
                "unit": item.unit or original.unit,
            }
        )
        enriched_items.append(enriched)

    ret = MaterialReturn(
        withdrawal_id=data.withdrawal_id,
        contractor_id=withdrawal.contractor_id,
        contractor_name=withdrawal.contractor_name,
        billing_entity=withdrawal.billing_entity,
        job_id=withdrawal.job_id,
        items=enriched_items,
        reason=data.reason,
        notes=data.notes,
        processed_by_id=current_user.id,
        processed_by_name=current_user.name,
    )
    ret.compute_totals(tax_rate=tax_rate)
    ret.organization_id = org_id

    async with transaction():
        for item in enriched_items:
            await restock_as_return(
                product_id=item.product_id,
                sku=item.sku,
                product_name=item.name,
                quantity=item.quantity,
                user_id=current_user.id,
                user_name=current_user.name,
                reference_id=ret.id,
                unit=item.unit,
                transaction_type=StockTransactionType.RETURN,
            )

        await return_repo.insert(ret)

        w_dept_map = {
            wi.product_id: getattr(wi, "department_name", None) for wi in withdrawal.items
        }
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
            performed_by_user_id=current_user.id,
        )

        result = ret.model_dump()

        if withdrawal.invoice_id:
            _log = logging.getLogger(__name__)
            try:
                cn = await insert_credit_note(
                    return_id=ret.id,
                    invoice_id=withdrawal.invoice_id,
                    items=enriched_items,
                    subtotal=ret.subtotal,
                    tax=ret.tax,
                    total=ret.total,
                )
                result["credit_note_id"] = cn.id

                try:
                    await _apply_cn(
                        credit_note_id=cn.id,
                        performed_by_user_id=current_user.id,
                    )
                except Exception:
                    _log.warning(
                        "Auto-apply credit note %s failed, credit note still created",
                        cn.id,
                        exc_info=True,
                    )
            except (ValueError, RuntimeError, OSError):
                _log.warning(
                    "Credit note creation failed for return %s, continuing without credit note",
                    ret.id,
                    exc_info=True,
                )

        return result
