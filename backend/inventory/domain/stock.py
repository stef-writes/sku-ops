"""Stock ledger - immutable inventory transaction records."""

from enum import StrEnum

from shared.kernel.entity import Entity
from shared.kernel.stock import StockDecrement

__all__ = ["StockDecrement", "StockTransaction", "StockTransactionType"]


class StockTransactionType(StrEnum):
    """Types of stock movements."""

    WITHDRAWAL = "withdrawal"  # POS sale / contractor withdrawal
    RECEIVING = "receiving"  # Goods received from vendor
    ADJUSTMENT = "adjustment"  # Manual count correction
    RETURN = "return"  # Customer/vendor return
    TRANSFER = "transfer"  # Inter-location transfer (future)
    IMPORT = "import"  # Bulk import (receipt/PDF)


class StockTransaction(Entity):
    """Immutable record of a single product quantity change."""

    product_id: str
    sku: str
    product_name: str = ""
    quantity_delta: float
    quantity_before: float
    quantity_after: float
    unit: str = "each"
    transaction_type: StockTransactionType
    reference_id: str | None = None
    reference_type: str | None = None
    reason: str | None = None
    user_id: str
    user_name: str = ""
