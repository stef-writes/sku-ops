"""Base entity types — the mechanical pattern every domain entity shares."""
from datetime import UTC, datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class Entity(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid4()))
    organization_id: str = "default"
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class AuditedEntity(Entity):
    updated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
