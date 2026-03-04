"""Purchase order domain models."""
from typing import List, Optional

from pydantic import BaseModel


class CreatePORequest(BaseModel):
    vendor_name: str
    create_vendor_if_missing: bool = True
    department_id: Optional[str] = None
    document_date: Optional[str] = None
    total: Optional[float] = None
    products: List[dict]


class ReceiveItemsRequest(BaseModel):
    items: List[dict]  # [{"id": item_id, "delivered_qty": qty}]


class MarkDeliveryRequest(BaseModel):
    item_ids: List[str]
