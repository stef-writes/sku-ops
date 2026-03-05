"""Stock ledger - immutable inventory transaction records."""
from enum import Enum
from typing import Optional

from pydantic import BaseModel

from kernel.entity import Entity


class StockDecrement(BaseModel):
    """What inventory needs to know to reduce stock — no pricing or billing."""
    product_id: str
    sku: str
    name: str
    quantity: float
    unit: str = "each"


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
    quantity_delta: float
    quantity_before: float
    quantity_after: float
    unit: str = "each"
    transaction_type: StockTransactionType
    reference_id: Optional[str] = None
    reference_type: Optional[str] = None
    reason: Optional[str] = None
    user_id: str
    user_name: str = ""
