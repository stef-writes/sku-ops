"""Withdrawal service: encapsulates creation of material withdrawals with transaction."""
from typing import Callable, Awaitable, Optional

from kernel.types import CurrentUser
from shared.infrastructure.database import transaction
from inventory.domain.stock import StockDecrement
from catalog.domain.units import are_compatible, convert_quantity
from operations.domain.withdrawal import MaterialWithdrawal, MaterialWithdrawalCreate
from operations.infrastructure.withdrawal_repo import withdrawal_repo as _default_withdrawal_repo
from operations.ports.withdrawal_repo_port import WithdrawalRepoPort
from finance.application.ledger_service import record_withdrawal as _record_ledger
from jobs.infrastructure.job_repo import job_repo as _job_repo
from identity.application.billing_entity_service import ensure_billing_entity

CreateInvoiceFn = Optional[Callable[..., Awaitable[dict]]]
ListProductsFn = Callable[..., Awaitable[list]]
StockChangesFn = Callable[..., Awaitable[None]]


def _convert_price_per_unit(
    price_per_base: float, base_unit: str, requested_unit: str,
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
    conn=None,
) -> dict:
    """Create a material withdrawal with atomic stock decrement and optional invoice.

    Returns withdrawal dict with optional invoice_id.
    """
    org_id = current_user.organization_id
    if data.job_id:
        await _job_repo.ensure_job(data.job_id, org_id)
    products = await list_products(organization_id=org_id)
    product_map = {p["id"]: p for p in products}
    dept_map = {p["id"]: p.get("department_name", "") for p in products}
    enriched_items = []
    for item in data.items:
        p = product_map.get(item.product_id, {})
        base_unit = (p.get("base_unit") or "each").lower()
        req_unit = (item.unit or base_unit).lower()

        updates: dict = {}
        if item.cost == 0.0 and p.get("cost", 0):
            updates["cost"] = _convert_price_per_unit(p["cost"], base_unit, req_unit)
        elif item.cost != 0.0 and req_unit != base_unit and are_compatible(base_unit, req_unit):
            updates["cost"] = _convert_price_per_unit(p.get("cost", item.cost), base_unit, req_unit)

        if item.unit_price == 0.0 and p.get("price", 0):
            updates["unit_price"] = _convert_price_per_unit(p["price"], base_unit, req_unit)
        elif item.unit_price != 0.0 and req_unit != base_unit and are_compatible(base_unit, req_unit):
            updates["unit_price"] = _convert_price_per_unit(p.get("price", item.unit_price), base_unit, req_unit)

        if updates:
            item = item.model_copy(update=updates)
        enriched_items.append(item)
    data = data.model_copy(update={"items": enriched_items})

    billing_entity_name = contractor.get("billing_entity", "")
    billing_entity_id = contractor.get("billing_entity_id")
    if billing_entity_name and not billing_entity_id:
        be = await ensure_billing_entity(billing_entity_name, org_id)
        billing_entity_id = be.get("id") if be else None

    withdrawal = MaterialWithdrawal(
        items=data.items,
        job_id=data.job_id,
        service_address=data.service_address,
        notes=data.notes,
        subtotal=0, tax=0, total=0, cost_total=0,
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

    async def _do_create(tx_conn):
        decrements = [
            StockDecrement(
                product_id=i.product_id, sku=i.sku, name=i.name,
                quantity=i.quantity, unit=i.unit or "each",
            )
            for i in data.items
        ]
        await process_stock_changes(
            items=decrements,
            withdrawal_id=withdrawal.id,
            user_id=current_user.id,
            user_name=current_user.name,
            organization_id=org_id,
            conn=tx_conn,
        )

        withdrawal.organization_id = org_id
        await withdrawal_repo.insert(withdrawal, conn=tx_conn)

        ledger_items = [
            {"product_id": i.product_id, "quantity": i.quantity,
             "unit_price": i.unit_price, "cost": i.cost,
             "department_name": dept_map.get(i.product_id)}
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
            organization_id=org_id,
            performed_by_user_id=current_user.id,
            conn=tx_conn,
        )

        if create_invoice:
            try:
                inv = await create_invoice(withdrawal_ids=[withdrawal.id], conn=tx_conn)
                result = withdrawal.model_dump()
                result["invoice_id"] = inv.get("id")
                return result
            except ValueError:
                pass
        return withdrawal.model_dump()

    if conn is not None:
        return await _do_create(conn)
    async with transaction() as tx_conn:
        return await _do_create(tx_conn)
