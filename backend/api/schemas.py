"""API request/response schemas."""
from typing import List, Optional

from pydantic import BaseModel


class SuggestUomRequest(BaseModel):
    name: str
    description: Optional[str] = None


class ChatRequest(BaseModel):
    message: str
    messages: Optional[List[dict]] = None  # prior conversation [{role, content}]


class DocumentImportRequest(BaseModel):
    vendor_name: str
    create_vendor_if_missing: bool = True
    department_id: Optional[str] = None
    products: List[dict]


class CreatePaymentRequest(BaseModel):
    withdrawal_id: str
    origin_url: str
