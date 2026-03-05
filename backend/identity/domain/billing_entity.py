"""Billing entity domain models — the "who gets billed" master record."""
from typing import Optional

from pydantic import BaseModel

from kernel.entity import AuditedEntity


class BillingEntity(AuditedEntity):
    """An organization or person that receives invoices."""
    name: str
    contact_name: str = ""
    contact_email: str = ""
    billing_address: str = ""
    payment_terms: str = "net_30"
    xero_contact_id: Optional[str] = None
    is_active: bool = True


class BillingEntityCreate(BaseModel):
    name: str
    contact_name: str = ""
    contact_email: str = ""
    billing_address: str = ""
    payment_terms: str = "net_30"


class BillingEntityUpdate(BaseModel):
    name: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    billing_address: Optional[str] = None
    payment_terms: Optional[str] = None
    xero_contact_id: Optional[str] = None
    is_active: Optional[bool] = None
