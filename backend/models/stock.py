"""Stock ledger - immutable inventory transaction records."""
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class StockTransactionType(str, Enum):
    """Types of stock movements."""
    WITHDRAWAL = "withdrawal"      # POS sale / contractor withdrawal
    RECEIVING = "receiving"       # Goods received from vendor
    ADJUSTMENT = "adjustment"     # Manual count correction
    RETURN = "return"             # Customer/vendor return
    TRANSFER = "transfer"         # Inter-location transfer (future)
    IMPORT = "import"             # Bulk import (receipt/PDF)


class StockTransaction(BaseModel):
    """Immutable record of a single product quantity change."""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid4()))
    product_id: str
    sku: str
    product_name: str = ""
    # Movement
    quantity_delta: int  # Negative = out, positive = in
    quantity_before: int
    quantity_after: int
    # Context
    transaction_type: StockTransactionType
    reference_id: Optional[str] = None   # withdrawal_id, po_id, etc.
    reference_type: Optional[str] = None  # "withdrawal", "receiving", etc.
    reason: Optional[str] = None         # For adjustments
    # Audit
    user_id: str
    user_name: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
