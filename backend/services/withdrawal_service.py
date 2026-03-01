"""
Withdrawal service: encapsulates creation of material withdrawals with transaction.
"""
from typing import Optional

from fastapi import HTTPException

from db import transaction
from models import MaterialWithdrawal, MaterialWithdrawalCreate
from repositories import invoice_repo, withdrawal_repo
from services.inventory import process_withdrawal_stock_changes, InsufficientStockError


async def create_withdrawal(
    data: MaterialWithdrawalCreate,
    contractor: dict,
    current_user: dict,
) -> dict:
    """
    Create a material withdrawal with atomic stock decrement and optional invoice.
    Returns withdrawal dict with optional invoice_id.
    """
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

    async with transaction() as conn:
        try:
            await process_withdrawal_stock_changes(
                items=data.items,
                withdrawal_id=withdrawal.id,
                user_id=current_user["id"],
                user_name=current_user.get("name", ""),
                conn=conn,
            )
        except InsufficientStockError as e:
            raise HTTPException(status_code=400, detail=str(e))

        await withdrawal_repo.insert(withdrawal.model_dump(), conn=conn)

        try:
            inv = await invoice_repo.create_from_withdrawals([withdrawal.id], conn=conn)
            result = withdrawal.model_dump()
            result["invoice_id"] = inv.get("id")
            return result
        except ValueError:
            pass
    return withdrawal.model_dump()
