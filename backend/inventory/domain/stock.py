"""Stock ledger - immutable inventory transaction records."""
from enum import Enum
from typing import Optional

from kernel.entity import Entity


class StockTransactionType(str, Enum):
    """Types of stock movements."""
    WITHDRAWAL = "withdrawal"      # POS sale / contractor withdrawal
    RECEIVING = "receiving"       # Goods received from vendor
    ADJUSTMENT = "adjustment"     # Manual count correction
    RETURN = "return"             # Customer/vendor return
    TRANSFER = "transfer"         # Inter-location transfer (future)
    IMPORT = "import"             # Bulk import (receipt/PDF)


class StockTransaction(Entity):
    """Immutable record of a single product quantity change."""
    product_id: str
    sku: str
    product_name: str = ""
    quantity_delta: int
    quantity_before: int
    quantity_after: int
    transaction_type: StockTransactionType
    reference_id: Optional[str] = None
    reference_type: Optional[str] = None
    reason: Optional[str] = None
    user_id: str
    user_name: str = ""
