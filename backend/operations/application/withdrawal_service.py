"""
Withdrawal service: encapsulates creation of material withdrawals with transaction.
"""
from typing import Optional

from fastapi import HTTPException

from shared.infrastructure.database import get_connection, transaction
from operations.domain.withdrawal import MaterialWithdrawal, MaterialWithdrawalCreate
from finance.application.invoice_service import create_invoice_from_withdrawals
from catalog.application.queries import list_products
from operations.infrastructure.withdrawal_repo import withdrawal_repo
from shared.domain.exceptions import InsufficientStockError
from inventory.application.inventory_service import process_withdrawal_stock_changes


async def create_withdrawal(
    data: MaterialWithdrawalCreate,
    contractor: dict,
    current_user: dict,
    conn=None,
) -> dict:
    """
    Create a material withdrawal with atomic stock decrement and optional invoice.
    Returns withdrawal dict with optional invoice_id.
    If conn is provided, runs inside that transaction (no commit).
    """
    # Enrich item costs from product catalog if not set by the caller
    org_id = current_user.get("organization_id") or "default"
    products = await list_products(organization_id=org_id)
    cost_map = {p["id"]: p.get("cost", 0.0) for p in products}
    enriched_items = []
    for item in data.items:
        if item.cost == 0.0 and item.product_id in cost_map:
            item = item.model_copy(update={"cost": cost_map[item.product_id]})
        enriched_items.append(item)
    data = data.model_copy(update={"items": enriched_items})

    subtotal = sum(item.subtotal for item in data.items)
    cost_total = sum(item.cost * item.quantity for item in data.items)
    tax = round(subtotal * 0.08, 2)
    total = round(subtotal + tax, 2)

    withdrawal = MaterialWithdrawal(
        items=data.items,
        job_id=data.job_id,
        service_address=data.service_address,
        notes=data.notes,
        subtotal=subtotal,
        tax=tax,
        total=total,
        cost_total=cost_total,
        contractor_id=contractor["id"],
        contractor_name=contractor.get("name", ""),
        contractor_company=contractor.get("company", ""),
        billing_entity=contractor.get("billing_entity", ""),
        payment_status="unpaid",
        processed_by_id=current_user["id"],
        processed_by_name=current_user.get("name", ""),
    )

    async def _do_create(tx_conn):
        try:
            await process_withdrawal_stock_changes(
                items=data.items,
                withdrawal_id=withdrawal.id,
                user_id=current_user["id"],
                user_name=current_user.get("name", ""),
                organization_id=current_user.get("organization_id") or "default",
                conn=tx_conn,
            )
        except InsufficientStockError as e:
            raise HTTPException(status_code=400, detail=str(e))

        w_dict = withdrawal.model_dump()
        w_dict["organization_id"] = current_user.get("organization_id") or "default"
        await withdrawal_repo.insert(w_dict, conn=tx_conn)

        try:
            inv = await create_invoice_from_withdrawals([withdrawal.id], conn=tx_conn)
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
