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
    xero_contact_id: str | None = None
    is_active: bool = True


class BillingEntityCreate(BaseModel):
    name: str
    contact_name: str = ""
    contact_email: str = ""
    billing_address: str = ""
    payment_terms: str = "net_30"


class BillingEntityUpdate(BaseModel):
    name: str | None = None
    contact_name: str | None = None
    contact_email: str | None = None
    billing_address: str | None = None
    payment_terms: str | None = None
    xero_contact_id: str | None = None
    is_active: bool | None = None
