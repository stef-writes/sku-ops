"""Shared kernel — domain primitives used across all bounded contexts.

Modules:
    entity  — Entity, AuditedEntity base classes
    types   — CurrentUser, LineItem, Address, round_money
    errors  — DomainError, ResourceNotFoundError, InvalidTransitionError
    events  — Event, SHUTDOWN, is_shutdown, event type constants
"""

from shared.kernel import events
from shared.kernel.entity import AuditedEntity, Entity
from shared.kernel.errors import DomainError, InvalidTransitionError, ResourceNotFoundError
from shared.kernel.events import Event
from shared.kernel.types import Address, CurrentUser, LineItem, round_money

__all__ = [
    "Address",
    "AuditedEntity",
    "CurrentUser",
    "DomainError",
    "Entity",
    "Event",
    "InvalidTransitionError",
    "LineItem",
    "ResourceNotFoundError",
    "events",
    "round_money",
]
