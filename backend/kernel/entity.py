"""Base entity types — the mechanical pattern every domain entity shares."""
from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class Entity(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class AuditedEntity(Entity):
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
