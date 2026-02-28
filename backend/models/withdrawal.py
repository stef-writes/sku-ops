"""Material withdrawal (POS) models."""
from datetime import datetime, timezone
from typing import List, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class WithdrawalItem(BaseModel):
    product_id: str
    sku: str
    name: str
    quantity: int
    price: float
    cost: float = 0.0
    subtotal: float
    unit: str = "each"  # sell_uom from product for display


class MaterialWithdrawalCreate(BaseModel):
    items: List[WithdrawalItem]
    job_id: str
    service_address: str
    notes: Optional[str] = None


class MaterialWithdrawal(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid4()))
    items: List[WithdrawalItem]
    job_id: str
    service_address: str
    notes: Optional[str] = None
    subtotal: float
    tax: float
    total: float
    cost_total: float
    contractor_id: str
    contractor_name: str = ""
    contractor_company: str = ""
    billing_entity: str = ""
    payment_status: str = "unpaid"
    invoice_id: Optional[str] = None
    paid_at: Optional[str] = None
    processed_by_id: str
    processed_by_name: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
