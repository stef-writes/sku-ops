"""Material request models - contractor pick list before staff processes into withdrawal."""
from typing import List, Optional

from pydantic import BaseModel

from kernel.entity import Entity

from .withdrawal import WithdrawalItem


class MaterialRequestCreate(BaseModel):
    items: list[WithdrawalItem]
    job_id: str | None = None
    service_address: str | None = None
    notes: str | None = None


class MaterialRequestProcess(BaseModel):
    job_id: str | None = None
    service_address: str | None = None
    notes: str | None = None


class MaterialRequest(Entity):
    contractor_id: str
    contractor_name: str = ""
    items: list[WithdrawalItem]
    status: str = "pending"
    withdrawal_id: str | None = None
    job_id: str | None = None
    service_address: str | None = None
    notes: str | None = None
    processed_at: str | None = None
    processed_by_id: str | None = None
    organization_id: str = "default"
