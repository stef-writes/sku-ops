"""Structured session state — working memory for follow-up and drill-down.

Entities and last_topic are stored per session for context injection
on the next turn (e.g. "tell me more about that product").
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime


@dataclass
class EntityRef:
    """Reference to an entity recently mentioned in the conversation."""

    type: str  # product, vendor, job, po
    id: str
    label: str  # display name


@dataclass
class SessionState:
    """Working memory for a chat session."""

    entities: list[EntityRef]
    last_topic: str | None
    updated_at: datetime
