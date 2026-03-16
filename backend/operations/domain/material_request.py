"""Material request models - contractor pick list before staff processes into withdrawal."""

from pydantic import BaseModel

from operations.domain.enums import MaterialRequestStatus
from operations.domain.withdrawal import WithdrawalItem
from shared.kernel.entity import Entity


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
    status: MaterialRequestStatus = MaterialRequestStatus.PENDING
    withdrawal_id: str | None = None
    job_id: str | None = None
    service_address: str | None = None
    notes: str | None = None
    processed_at: str | None = None
    processed_by_id: str | None = None
