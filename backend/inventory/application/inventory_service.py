"""
Inventory service: atomic stock operations and stock ledger.

Every quantity change creates an immutable StockTransaction record.
Withdrawals use atomic UPDATE with quantity guard to prevent overselling.
Unit conversion happens here — stock is always stored in the product's base_unit.
"""

from datetime import UTC, datetime
from uuid import uuid4

from catalog.application.queries import (
    add_product_quantity,
    atomic_adjust_product,
    atomic_decrement_product,
    get_product_by_id,
    increment_product_quantity,
)
from finance.application.ledger_service import record_adjustment as _record_ledger_adjustment
from inventory.domain.errors import InsufficientStockError, NegativeStockError
from inventory.domain.stock import StockDecrement, StockTransaction, StockTransactionType
from inventory.infrastructure.stock_repo import stock_repo as _default_stock_repo
from inventory.ports.stock_repo_port import StockRepoPort
from kernel.errors import ResourceNotFoundError
from shared.infrastructure.config import DEFAULT_ORG_ID
from shared.kernel.units import are_compatible, convert_quantity


async def _record_stock_transaction(
    product_id: str,
    sku: str,
    product_name: str,
    quantity_delta: float,
    quantity_before: float,
    transaction_type: StockTransactionType,
    user_id: str,
    user_name: str,
    reference_id: str | None = None,
    reason: str | None = None,
    unit: str = "each",
    organization_id: str | None = None,
    repo: StockRepoPort = _default_stock_repo,
) -> None:
    """Append an immutable transaction to the stock ledger."""
    quantity_after = round(quantity_before + quantity_delta, 6)
    tx = StockTransaction(
        product_id=product_id,
        sku=sku,
        product_name=product_name,
        quantity_delta=quantity_delta,
        quantity_before=quantity_before,
        quantity_after=quantity_after,
        unit=unit,
        transaction_type=transaction_type,
        reference_id=reference_id,
        reference_type=transaction_type.value,
        reason=reason,
        user_id=user_id,
        user_name=user_name,
    )
    tx.organization_id = organization_id or DEFAULT_ORG_ID
    await repo.insert_transaction(tx)


async def process_withdrawal_stock_changes(
    items: list[StockDecrement],
    withdrawal_id: str,
    user_id: str,
    user_name: str,
    organization_id: str | None = None,
) -> None:
    """
    Atomically decrement product quantities for a withdrawal.
    Converts from the requested unit to the product's base_unit before decrementing.
    Uses UPDATE with quantity guard to prevent overselling.
    Rolls back all completed decrements on any failure.
    """
    now = datetime.now(UTC).isoformat()
    completed: list[tuple[str, float]] = []

    try:
        for item in items:
            product = await get_product_by_id(item.product_id)
            base_unit = (product.base_unit if product else "each").lower()
            requested_unit = (item.unit or "each").lower()

            if requested_unit != base_unit and are_compatible(requested_unit, base_unit):
                canonical_qty = convert_quantity(item.quantity, requested_unit, base_unit)
            else:
                canonical_qty = item.quantity

            result = await atomic_decrement_product(item.product_id, canonical_qty, now)

            if not result:
                available = product.quantity if product else 0
                raise InsufficientStockError(
                    sku=item.sku, requested=item.quantity, available=available
                )

            quantity_before = result.quantity + canonical_qty
            await _record_stock_transaction(
                product_id=item.product_id,
                sku=item.sku,
                product_name=item.name,
                quantity_delta=-canonical_qty,
                quantity_before=quantity_before,
                transaction_type=StockTransactionType.WITHDRAWAL,
                user_id=user_id,
                user_name=user_name,
                reference_id=withdrawal_id,
                unit=base_unit,
                organization_id=organization_id,
            )
            completed.append((item.product_id, canonical_qty))

    except Exception:
        for product_id, qty in completed:
            await increment_product_quantity(product_id, qty, now)
        raise


async def process_receiving_stock_changes(
    product_id: str,
    sku: str,
    product_name: str,
    quantity: float,
    user_id: str,
    user_name: str,
    reference_id: str | None = None,
    unit: str = "each",
    organization_id: str | None = None,
    transaction_type: StockTransactionType = StockTransactionType.RECEIVING,
) -> None:
    """Add stock (receiving, import, return) and record transaction.

    Converts from the supplied unit to the product's base_unit before adding.
    """
    product = await get_product_by_id(product_id)
    base_unit = (product.base_unit if product else "each").lower()
    incoming_unit = (unit or "each").lower()

    if incoming_unit != base_unit and are_compatible(incoming_unit, base_unit):
        canonical_qty = convert_quantity(quantity, incoming_unit, base_unit)
    else:
        canonical_qty = quantity

    now = datetime.now(UTC).isoformat()
    result = await add_product_quantity(product_id, canonical_qty, now)
    if not result:
        raise ResourceNotFoundError("Product", product_id)

    quantity_before = result.quantity - canonical_qty
    await _record_stock_transaction(
        product_id=product_id,
        sku=sku,
        product_name=product_name,
        quantity_delta=canonical_qty,
        quantity_before=quantity_before,
        transaction_type=transaction_type,
        user_id=user_id,
        user_name=user_name,
        reference_id=reference_id,
        unit=base_unit,
        organization_id=organization_id,
    )


async def process_import_stock_changes(
    product_id: str,
    sku: str,
    product_name: str,
    quantity: float,
    user_id: str,
    user_name: str,
    unit: str = "each",
    organization_id: str | None = None,
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
        unit=unit or "each",
        organization_id=organization_id,
    )


async def get_stock_history(
    product_id: str,
    limit: int = 50,
) -> list[StockTransaction]:
    """Get stock transaction history for a product."""
    return await _default_stock_repo.list_by_product(product_id, limit)


async def process_adjustment_stock_changes(
    product_id: str,
    quantity_delta: float,
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
    now = datetime.now(UTC).isoformat()
    product = await get_product_by_id(product_id)
    if not product:
        raise ResourceNotFoundError("Product", product_id)

    base_unit = product.base_unit.lower()
    result = await atomic_adjust_product(product_id, quantity_delta, now)
    if not result:
        raise NegativeStockError(product_id, current=product.quantity, delta=quantity_delta)

    quantity_after = result.quantity
    quantity_before = quantity_after - quantity_delta
    adjustment_id = str(uuid4())
    await _record_stock_transaction(
        product_id=product_id,
        sku=product.sku,
        product_name=product.name,
        quantity_delta=quantity_delta,
        quantity_before=quantity_before,
        transaction_type=StockTransactionType.ADJUSTMENT,
        user_id=user_id,
        user_name=user_name,
        reference_id=adjustment_id,
        reason=reason,
        unit=base_unit,
    )

    await _record_ledger_adjustment(
        adjustment_ref_id=adjustment_id,
        product_id=product_id,
        product_cost=product.cost,
        quantity_delta=quantity_delta,
        department=product.department_name,
        organization_id=product.organization_id,
        reason=reason,
        performed_by_user_id=user_id,
    )


async def restock_as_return(
    product_id: str,
    sku: str,
    product_name: str,
    quantity: float,
    user_id: str,
    user_name: str,
    reference_id: str | None = None,
    unit: str = "each",
    organization_id: str | None = None,
) -> None:
    """Restock inventory as a customer/vendor return (RETURN transaction type)."""
    await process_receiving_stock_changes(
        product_id=product_id,
        sku=sku,
        product_name=product_name,
        quantity=quantity,
        user_id=user_id,
        user_name=user_name,
        reference_id=reference_id,
        unit=unit,
        organization_id=organization_id,
        transaction_type=StockTransactionType.RETURN,
    )
