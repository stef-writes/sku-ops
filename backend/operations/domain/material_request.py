"""Material request models - contractor pick list before staff processes into withdrawal."""

from pydantic import BaseModel

from operations.domain.withdrawal import WithdrawalItem
from shared.kernel.constants import DEFAULT_ORG_ID
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
    status: str = "pending"
    withdrawal_id: str | None = None
    job_id: str | None = None
    service_address: str | None = None
    notes: str | None = None
    processed_at: str | None = None
    processed_by_id: str | None = None
    organization_id: str = DEFAULT_ORG_ID
