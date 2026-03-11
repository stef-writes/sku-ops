"""Cross-cutting domain errors — no HTTP coupling.

Subclasses set status_hint so the API layer can map to HTTP status codes
with a single exception handler.
"""


class DomainError(Exception):
    """Base for all domain-level errors."""

    status_hint: int = 400


class ResourceNotFoundError(DomainError):
    """Raised when a required resource (product, department, etc.) is not found."""

    status_hint = 404

    def __init__(self, resource_type: str, resource_id: str):
        self.resource_type = resource_type
        self.resource_id = resource_id
        super().__init__(f"{resource_type} not found: {resource_id}")


class InvalidTransitionError(DomainError):
    """Raised when a state transition is not allowed."""

    status_hint = 409

    def __init__(self, entity: str, current: str, target: str):
        self.entity = entity
        self.current = current
        self.target = target
        super().__init__(f"{entity} cannot transition from {current} to {target}")
