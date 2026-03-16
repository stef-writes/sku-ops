"""Return service: validate against original withdrawal, restock, emit events."""

from __future__ import annotations

from typing import TYPE_CHECKING

from finance.application.ledger_service import record_return as _record_return_ledger
from finance.application.org_settings_service import get_org_settings
from inventory.application.inventory_service import restock_as_return
from operations.application.queries import get_withdrawal_by_id
from operations.domain.returns import MaterialReturn, ReturnCreate, ReturnItem
from operations.infrastructure.return_repo import return_repo as _default_return_repo
from shared.infrastructure.database import get_connection, get_org_id, transaction
from shared.infrastructure.domain_events import dispatch
from shared.kernel.domain_events import InventoryChanged, ReturnCreated
from shared.kernel.errors import DomainError, ResourceNotFoundError
from shared.kernel.event_payloads import LedgerItem

if TYPE_CHECKING:
    from operations.ports.return_repo_port import ReturnRepoPort
    from shared.kernel.types import CurrentUser


async def create_return(
    data: ReturnCreate,
    current_user: CurrentUser,
    *,
    return_repo: ReturnRepoPort = _default_return_repo,
) -> MaterialReturn:
    """Process a return against a previous withdrawal.

    The transaction writes: inventory restock, return row, ledger entries.
    All three commit atomically — a failure rolls back all three.

    Post-commit (best-effort): credit note creation, WS push.
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

    w_dept_map = {wi.product_id: getattr(wi, "category_name", None) for wi in withdrawal.items}

    ret = MaterialReturn(
        withdrawal_id=data.withdrawal_id,
        contractor_id=withdrawal.contractor_id,
        contractor_name=withdrawal.contractor_name,
        billing_entity=withdrawal.billing_entity,
        job_id=withdrawal.job_id,
        items=[],  # filled after validation inside transaction
        reason=data.reason,
        notes=data.notes,
        processed_by_id=current_user.id,
        processed_by_name=current_user.name,
        organization_id=org_id,
    )

    enriched_items: list[ReturnItem] = []
    product_ids: tuple[str, ...] = ()
    ledger_items: tuple[LedgerItem, ...] = ()

    async with transaction():
        # Lock the withdrawal row to serialize concurrent returns for the same withdrawal.
        conn = get_connection()
        await conn.execute(
            "SELECT id FROM withdrawals WHERE id = $1 FOR UPDATE",
            (data.withdrawal_id,),
        )

        # Re-read already-returned quantities inside the transaction (after lock).
        existing_returns = await return_repo.list_by_withdrawal(data.withdrawal_id)
        already_returned: dict[str, float] = {}
        for er in existing_returns:
            for ri in er.items:
                already_returned[ri.product_id] = (
                    already_returned.get(ri.product_id, 0) + ri.quantity
                )

        enriched_items = []
        for item in data.items:
            original = w_item_map.get(item.product_id)
            if not original:
                raise DomainError(
                    f"Product {item.product_id} ({item.sku}) not on original withdrawal"
                )

            max_returnable = original.quantity - already_returned.get(item.product_id, 0)
            if item.quantity > max_returnable:
                raise DomainError(
                    f"Cannot return {item.quantity} of {item.name} — "
                    f"max returnable is {max_returnable}"
                )

            enriched_items.append(
                item.model_copy(
                    update={
                        "unit_price": item.unit_price or original.unit_price,
                        "cost": item.cost or original.cost,
                        "unit": item.unit or original.unit,
                    }
                )
            )

        ret.items = enriched_items
        ret.compute_totals(tax_rate=tax_rate)

        product_ids = tuple(item.product_id for item in enriched_items)
        ledger_items = tuple(
            LedgerItem(
                product_id=item.product_id,
                quantity=item.quantity,
                unit=item.unit or "each",
                unit_price=item.unit_price,
                cost=item.cost,
                category_name=w_dept_map.get(item.product_id),
            )
            for item in enriched_items
        )

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
            )
        await return_repo.insert(ret)
        await _record_return_ledger(
            return_id=ret.id,
            items=list(ledger_items),
            tax=ret.tax,
            total=ret.total,
            job_id=withdrawal.job_id or "",
            billing_entity=withdrawal.billing_entity or "",
            contractor_id=withdrawal.contractor_id,
            performed_by_user_id=current_user.id,
        )

    await dispatch(
        ReturnCreated(
            org_id=org_id,
            return_id=ret.id,
            withdrawal_id=data.withdrawal_id,
            contractor_id=withdrawal.contractor_id,
            job_id=withdrawal.job_id or "",
            billing_entity=withdrawal.billing_entity or "",
            tax=ret.tax,
            total=ret.total,
            performed_by_user_id=current_user.id,
            product_ids=product_ids,
            ledger_items=ledger_items,
            invoice_id=withdrawal.invoice_id,
        )
    )
    await dispatch(
        InventoryChanged(
            org_id=org_id,
            product_ids=product_ids,
            change_type="return",
        )
    )

    return ret
