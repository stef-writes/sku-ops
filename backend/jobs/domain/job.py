"""Job domain models — master record for job/project tracking."""

from enum import StrEnum

from pydantic import BaseModel

from shared.kernel.entity import AuditedEntity


class JobStatus(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class Job(AuditedEntity):
    """A job/project that withdrawals, returns, and invoices are charged against."""

    code: str
    name: str = ""
    billing_entity_id: str | None = None
    status: str = JobStatus.ACTIVE
    service_address: str = ""
    notes: str | None = None


class JobCreate(BaseModel):
    code: str
    name: str = ""
    service_address: str = ""
    notes: str | None = None


class JobUpdate(BaseModel):
    name: str | None = None
    status: str | None = None
    billing_entity_id: str | None = None
    service_address: str | None = None
    notes: str | None = None
