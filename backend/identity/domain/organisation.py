"""Organization (tenant) model."""
from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, Field


class Organization(BaseModel):
    """Organization (tenant) - one per supply yard / business unit."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    slug: str
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
