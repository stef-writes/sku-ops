"""
Inventory service: atomic stock operations and stock ledger.

Every quantity change creates an immutable StockTransaction record.
Withdrawals use atomic UPDATE with quantity guard to prevent overselling.
"""
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from fastapi import HTTPException

from shared.domain.exceptions import InsufficientStockError
from inventory.domain.stock import StockTransaction, StockTransactionType
from operations.domain.withdrawal import WithdrawalItem
from catalog.application.queries import (
    get_product_by_id, atomic_decrement_product,
    increment_product_quantity, add_product_quantity, atomic_adjust_product,
)
from inventory.infrastructure.stock_repo import stock_repo


async def _record_stock_transaction(
    product_id: str,
    sku: str,
    product_name: str,
    quantity_delta: int,
    quantity_before: int,
    transaction_type: StockTransactionType,
    user_id: str,
    user_name: str,
    reference_id: Optional[str] = None,
    reason: Optional[str] = None,
    organization_id: Optional[str] = None,
    conn=None,
) -> None:
    """Append an immutable transaction to the stock ledger."""
    quantity_after = quantity_before + quantity_delta
    tx = StockTransaction(
        product_id=product_id,
        sku=sku,
        product_name=product_name,
        quantity_delta=quantity_delta,
        quantity_before=quantity_before,
        quantity_after=quantity_after,
        transaction_type=transaction_type,
        reference_id=reference_id,
        reference_type=transaction_type.value,
        reason=reason,
        user_id=user_id,
        user_name=user_name,
    )
    tx_dict = tx.model_dump()
    tx_dict["organization_id"] = organization_id or "default"
    await stock_repo.insert_transaction(tx_dict, conn=conn)


async def process_withdrawal_stock_changes(
    items: List[WithdrawalItem],
    withdrawal_id: str,
    user_id: str,
    user_name: str,
    organization_id: Optional[str] = None,
    conn=None,
) -> None:
    """
    Atomically decrement product quantities for a withdrawal.
    Uses UPDATE with quantity guard to prevent overselling.
    Rolls back all completed decrements on any failure (InsufficientStockError or other).
    When conn is provided, runs inside that transaction (no commit).
    """
    now = datetime.now(timezone.utc).isoformat()
    completed: List[Tuple[str, int]] = []  # (product_id, quantity) for rollback

    try:
        for item in items:
            result = await atomic_decrement_product(
                item.product_id, item.quantity, now, conn=conn
            )

            if not result:
                product = await get_product_by_id(item.product_id, "quantity, sku", conn=conn)
                available = product.get("quantity", 0) if product else 0
                raise InsufficientStockError(
                    sku=item.sku, requested=item.quantity, available=available
                )

            quantity_before = result.get("quantity", 0) + item.quantity
            await _record_stock_transaction(
                product_id=item.product_id,
                sku=item.sku,
                product_name=item.name,
                quantity_delta=-item.quantity,
                quantity_before=quantity_before,
                transaction_type=StockTransactionType.WITHDRAWAL,
                user_id=user_id,
                user_name=user_name,
                reference_id=withdrawal_id,
                organization_id=organization_id,
                conn=conn,
            )
            completed.append((item.product_id, item.quantity))

    except Exception:
        # Roll back all completed decrements on any failure
        for product_id, qty in completed:
            await increment_product_quantity(product_id, qty, now, conn=conn)
        raise


async def process_receiving_stock_changes(
    product_id: str,
    sku: str,
    product_name: str,
    quantity: int,
    user_id: str,
    user_name: str,
    reference_id: Optional[str] = None,
) -> None:
    """Add stock (receiving, import, return) and record transaction."""
    now = datetime.now(timezone.utc).isoformat()
    result = await add_product_quantity(product_id, quantity, now)
    if not result:
        raise HTTPException(status_code=404, detail="Product not found")

    quantity_before = result.get("quantity", 0) - quantity
    await _record_stock_transaction(
        product_id=product_id,
        sku=sku,
        product_name=product_name,
        quantity_delta=quantity,
        quantity_before=quantity_before,
        transaction_type=StockTransactionType.RECEIVING,
        user_id=user_id,
        user_name=user_name,
        reference_id=reference_id,
    )


async def process_import_stock_changes(
    product_id: str,
    sku: str,
    product_name: str,
    quantity: int,
    user_id: str,
    user_name: str,
    organization_id: Optional[str] = None,
    conn=None,
) -> None:
    """Record stock added via bulk import (new product creation - no delta from existing)."""
    await _record_stock_transaction(
        product_id=product_id,
        sku=sku,
        product_name=product_name,
        quantity_delta=quantity,
        quantity_before=0,
        transaction_type=StockTransactionType.IMPORT,
        user_id=user_id,
        user_name=user_name,
        organization_id=organization_id,
        conn=conn,
    )


async def get_stock_history(
    product_id: str,
    limit: int = 50,
) -> List[dict]:
    """Get stock transaction history for a product."""
    return await stock_repo.list_by_product(product_id, limit)


async def process_adjustment_stock_changes(
    product_id: str,
    quantity_delta: int,
    reason: str,
    user_id: str,
    user_name: str,
) -> None:
    """
    Adjust stock (count, damage, correction) and record transaction.
    Uses atomic UPDATE to avoid TOCTOU race conditions.
    """
    if quantity_delta == 0:
        raise ValueError("quantity_delta must not be zero")
    now = datetime.now(timezone.utc).isoformat()
    product = await get_product_by_id(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    result = await atomic_adjust_product(product_id, quantity_delta, now)
    if not result:
        quantity_before = product.get("quantity", 0)
        raise HTTPException(
            status_code=400,
            detail=f"Cannot adjust: would result in negative stock (current: {quantity_before}, delta: {quantity_delta})",
        )

    quantity_after = result.get("quantity", 0)
    quantity_before = quantity_after - quantity_delta
    await _record_stock_transaction(
        product_id=product_id,
        sku=product.get("sku", ""),
        product_name=product.get("name", ""),
        quantity_delta=quantity_delta,
        quantity_before=quantity_before,
        transaction_type=StockTransactionType.ADJUSTMENT,
        user_id=user_id,
        user_name=user_name,
        reason=reason,
    )
