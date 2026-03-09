"""Shared kernel — domain primitives used across all bounded contexts.

Modules:
    entity  — Entity, AuditedEntity base classes
    types   — CurrentUser, LineItem, Address, round_money
    errors  — DomainError, ResourceNotFoundError, InvalidTransitionError
    events  — Event, SHUTDOWN, is_shutdown, event type constants
"""
from kernel import events
from kernel.entity import AuditedEntity, Entity
from kernel.errors import DomainError, InvalidTransitionError, ResourceNotFoundError
from kernel.events import Event
from kernel.types import Address, CurrentUser, LineItem, round_money

__all__ = [
    "Entity",
    "AuditedEntity",
    "CurrentUser",
    "LineItem",
    "Address",
    "round_money",
    "DomainError",
    "ResourceNotFoundError",
    "InvalidTransitionError",
    "Event",
    "events",
]
