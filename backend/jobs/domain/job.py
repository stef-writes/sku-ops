"""Job domain models — master record for job/project tracking."""
from enum import Enum
from typing import Optional

from pydantic import BaseModel

from kernel.entity import AuditedEntity


class JobStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class Job(AuditedEntity):
    """A job/project that withdrawals, returns, and invoices are charged against."""
    code: str
    name: str = ""
    billing_entity_id: Optional[str] = None
    status: str = JobStatus.ACTIVE
    service_address: str = ""
    notes: Optional[str] = None


class JobCreate(BaseModel):
    code: str
    name: str = ""
    service_address: str = ""
    notes: Optional[str] = None


class JobUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    billing_entity_id: Optional[str] = None
    service_address: Optional[str] = None
    notes: Optional[str] = None
