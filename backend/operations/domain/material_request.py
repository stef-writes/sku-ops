"""Material request models - contractor pick list before staff processes into withdrawal."""
from typing import List, Optional

from pydantic import BaseModel

from kernel.entity import Entity
from .withdrawal import WithdrawalItem


class MaterialRequestCreate(BaseModel):
    items: List[WithdrawalItem]
    job_id: Optional[str] = None
    service_address: Optional[str] = None
    notes: Optional[str] = None


class MaterialRequestProcess(BaseModel):
    job_id: str
    service_address: str
    notes: Optional[str] = None


class MaterialRequest(Entity):
    contractor_id: str
    contractor_name: str = ""
    items: List[WithdrawalItem]
    status: str = "pending"
    withdrawal_id: Optional[str] = None
    job_id: Optional[str] = None
    service_address: Optional[str] = None
    notes: Optional[str] = None
    processed_at: Optional[str] = None
    processed_by_id: Optional[str] = None
