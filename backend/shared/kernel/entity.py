"""Base entity types — the mechanical pattern every domain entity shares."""

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from shared.kernel.constants import DEFAULT_ORG_ID


class Entity(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid4()))
    organization_id: str = DEFAULT_ORG_ID
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class AuditedEntity(Entity):
    updated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
