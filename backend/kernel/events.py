"""Domain events — the canonical types and constants for everything that happens.

Every bounded context emits events through the event hub. This module defines
the ``Event`` value object, the event type constants (single source of truth),
and the visibility policy for contractor-scoped WebSocket delivery.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Event:
    type: str
    org_id: str
    data: dict[str, Any] = field(default_factory=dict)
    user_id: str = ""


SHUTDOWN = Event(type="__shutdown__", org_id="")
"""Sentinel event pushed to a subscriber queue to signal the sender to exit."""


def is_shutdown(event: Event) -> bool:
    return event.type == "__shutdown__"


# ── Event type constants ─────────────────────────────────────────────────────

INVENTORY_UPDATED = "inventory.updated"
CATALOG_UPDATED = "catalog.updated"

WITHDRAWAL_CREATED = "withdrawal.created"
WITHDRAWAL_UPDATED = "withdrawal.updated"

MATERIAL_REQUEST_CREATED = "material_request.created"
MATERIAL_REQUEST_PROCESSED = "material_request.processed"

CHAT_DONE = "chat.done"
CHAT_ERROR = "chat.error"
CHAT_CHUNK = "chat.chunk"
CHAT_COST = "chat.cost"
CHAT_TOOL_CALL = "chat.tool_call"

# ── Visibility policy ────────────────────────────────────────────────────────

CONTRACTOR_VISIBLE_EVENTS = frozenset({
    MATERIAL_REQUEST_CREATED,
    MATERIAL_REQUEST_PROCESSED,
    WITHDRAWAL_CREATED,
    WITHDRAWAL_UPDATED,
})
