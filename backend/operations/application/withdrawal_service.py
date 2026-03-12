"""Withdrawal service: encapsulates creation and payment workflows for material withdrawals."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from catalog.application.queries import list_products
from finance.application.billing_entity_service import ensure_billing_entity
from finance.application.invoice_service import (
    create_invoice_from_withdrawals,
    mark_paid_for_withdrawal,
)
from finance.application.ledger_service import record_payment as _record_payment
from finance.application.ledger_service import record_withdrawal as _record_ledger
from finance.application.org_settings_service import get_org_settings
from inventory.application.inventory_service import process_withdrawal_stock_changes
from jobs.application.job_service import ensure_job as _ensure_job
from operations.domain.withdrawal import MaterialWithdrawal, MaterialWithdrawalCreate
from operations.infrastructure.withdrawal_repo import withdrawal_repo as _default_withdrawal_repo
from shared.infrastructure.database import get_org_id, transaction
from shared.kernel.stock import StockDecrement
from shared.kernel.units import are_compatible, convert_quantity, cost_per_sell_unit

if TYPE_CHECKING:
    from operations.ports.withdrawal_repo_port import WithdrawalRepoPort
    from shared.kernel.types import CurrentUser

CreateInvoiceFn = Callable[..., Awaitable] | None
ListProductsFn = Callable[..., Awaitable[list]]
StockChangesFn = Callable[..., Awaitable[None]]

logger = logging.getLogger(__name__)


def _convert_price_per_unit(
    price_per_base: float,
    base_unit: str,
    requested_unit: str,
) -> float:
    """Convert a per-base_unit price to a per-requested_unit price.

    1 yard = 3 feet, so price_per_foot = price_per_yard / 3.
    Generalized: convert 1 of requested_unit to base_unit to get the ratio.
    """
    if base_unit == requested_unit:
        return price_per_base
    if not are_compatible(base_unit, requested_unit):
        return price_per_base
    base_qty_per_one_requested = convert_quantity(1, requested_unit, base_unit)
    return round(price_per_base * base_qty_per_one_requested, 6)


async def create_withdrawal(
    data: MaterialWithdrawalCreate,
    contractor: dict,
    current_user: CurrentUser,
    *,
    list_products: ListProductsFn,
    process_stock_changes: StockChangesFn,
    create_invoice: CreateInvoiceFn = None,
    withdrawal_repo: WithdrawalRepoPort = _default_withdrawal_repo,
    tax_rate: float = 0.10,
) -> dict:
    """Create a material withdrawal with atomic stock decrement and optional invoice.

    Returns withdrawal dict with optional invoice_id.
    """
    org_id = get_org_id()
    if data.job_id:
        await _ensure_job(data.job_id)
    products = await list_products()
    product_map = {p.id: p for p in products}
    dept_map = {p.id: p.department_name for p in products}
    enriched_items = []
    for item in data.items:
        p = product_map.get(item.product_id)
        base_unit = (p.base_unit if p else "each").lower()
        req_unit = (item.unit or base_unit).lower()
        sell_uom = (p.sell_uom if p else base_unit).lower()
        pack_qty = p.pack_qty if p else 1

        updates: dict = {}
        p_cost = p.cost if p else 0
        p_price = p.price if p else 0

        if item.cost == 0.0 and p_cost:
            updates["cost"] = _convert_price_per_unit(p_cost, base_unit, req_unit)
        elif item.cost != 0.0 and req_unit != base_unit and are_compatible(base_unit, req_unit):
            updates["cost"] = _convert_price_per_unit(p_cost or item.cost, base_unit, req_unit)

        if item.unit_price == 0.0 and p_price:
            updates["unit_price"] = _convert_price_per_unit(p_price, base_unit, req_unit)
        elif (
            item.unit_price != 0.0 and req_unit != base_unit and are_compatible(base_unit, req_unit)
        ):
            updates["unit_price"] = _convert_price_per_unit(
                p_price or item.unit_price, base_unit, req_unit
            )

        updates["sell_uom"] = sell_uom
        updates["sell_cost"] = cost_per_sell_unit(p_cost, base_unit, sell_uom, pack_qty)

        item = item.model_copy(update=updates)
        enriched_items.append(item)
    data = data.model_copy(update={"items": enriched_items})

    billing_entity_name = contractor.get("billing_entity", "")
    billing_entity_id = contractor.get("billing_entity_id")
    if billing_entity_name and not billing_entity_id:
        be = await ensure_billing_entity(billing_entity_name)
        billing_entity_id = be.id if be else None

    withdrawal = MaterialWithdrawal(
        items=data.items,
        job_id=data.job_id,
        service_address=data.service_address,
        notes=data.notes,
        subtotal=0,
        tax=0,
        total=0,
        cost_total=0,
        contractor_id=contractor["id"],
        contractor_name=contractor.get("name", ""),
        contractor_company=contractor.get("company", ""),
        billing_entity=billing_entity_name,
        billing_entity_id=billing_entity_id,
        payment_status="unpaid",
        processed_by_id=current_user.id,
        processed_by_name=current_user.name,
    )
    withdrawal.compute_totals(tax_rate=tax_rate)

    async with transaction():
        decrements = [
            StockDecrement(
                product_id=i.product_id,
                sku=i.sku,
                name=i.name,
                quantity=i.quantity,
                unit=i.unit or "each",
            )
            for i in data.items
        ]
        await process_stock_changes(
            items=decrements,
            withdrawal_id=withdrawal.id,
            user_id=current_user.id,
            user_name=current_user.name,
        )

        withdrawal.organization_id = org_id
        await withdrawal_repo.insert(withdrawal)

        ledger_items = [
            {
                "product_id": i.product_id,
                "quantity": i.quantity,
                "unit": i.unit or "each",
                "unit_price": i.unit_price,
                "cost": i.cost,
                "sell_uom": i.sell_uom,
                "sell_cost": i.sell_cost,
                "department_name": dept_map.get(i.product_id),
            }
            for i in data.items
        ]
        await _record_ledger(
            withdrawal_id=withdrawal.id,
            items=ledger_items,
            tax=withdrawal.tax,
            total=withdrawal.total,
            job_id=withdrawal.job_id,
            billing_entity=withdrawal.billing_entity,
            contractor_id=withdrawal.contractor_id,
            performed_by_user_id=current_user.id,
        )

        if create_invoice:
            try:
                inv = await create_invoice(withdrawal_ids=[withdrawal.id])
                result = withdrawal.model_dump()
                result["invoice_id"] = inv.id
                return result
            except ValueError:
                logger.warning(
                    "Auto-invoice failed for withdrawal %s, continuing without invoice",
                    withdrawal.id,
                    exc_info=True,
                )
        return withdrawal.model_dump()


async def create_withdrawal_wired(
    data: MaterialWithdrawalCreate,
    contractor: dict,
    current_user: CurrentUser,
) -> dict:
    """Wired version of create_withdrawal that resolves org settings and injects collaborators.

    Eliminates the duplicate do_create_withdrawal helpers in withdrawals.py and
    material_requests.py.
    """
    settings = await get_org_settings()
    return await create_withdrawal(
        data,
        contractor,
        current_user,
        list_products=list_products,
        process_stock_changes=process_withdrawal_stock_changes,
        create_invoice=create_invoice_from_withdrawals,
        tax_rate=settings.default_tax_rate,
    )


async def mark_single_withdrawal_paid(
    withdrawal_id: str,
    performed_by_user_id: str,
    withdrawal_repo: WithdrawalRepoPort = _default_withdrawal_repo,
) -> MaterialWithdrawal:
    """Mark a withdrawal as paid: update status, mark invoice paid, record ledger payment."""
    withdrawal = await withdrawal_repo.get_by_id(withdrawal_id)
    if not withdrawal:
        raise ValueError(f"Withdrawal {withdrawal_id} not found")
    paid_at = datetime.now(UTC).isoformat()
    result = await withdrawal_repo.mark_paid(withdrawal_id, paid_at)
    if not result:
        raise ValueError(f"Withdrawal {withdrawal_id} could not be marked paid")
    await mark_paid_for_withdrawal(withdrawal_id)
    await _record_payment(
        withdrawal_id=withdrawal_id,
        amount=withdrawal.total,
        billing_entity=withdrawal.billing_entity,
        contractor_id=withdrawal.contractor_id,
        performed_by_user_id=performed_by_user_id,
    )
    return result


async def bulk_mark_withdrawals_paid(
    withdrawal_ids: list[str],
    performed_by_user_id: str,
    withdrawal_repo: WithdrawalRepoPort = _default_withdrawal_repo,
) -> int:
    """Mark multiple withdrawals as paid in bulk.

    Returns count of updated withdrawals.
    """
    if len(withdrawal_ids) > 200:
        raise ValueError("Cannot mark more than 200 withdrawals at once")

    paid_at = datetime.now(UTC).isoformat()
    updated = await withdrawal_repo.bulk_mark_paid(withdrawal_ids, paid_at)
    for wid in withdrawal_ids:
        await mark_paid_for_withdrawal(wid)
        w = await withdrawal_repo.get_by_id(wid)
        if w:
            await _record_payment(
                withdrawal_id=wid,
                amount=w.total,
                billing_entity=w.billing_entity,
                contractor_id=w.contractor_id,
                performed_by_user_id=performed_by_user_id,
            )
    return updated
