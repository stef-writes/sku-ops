"""Inventory-specific domain errors."""
from kernel.errors import DomainError


class InsufficientStockError(DomainError):
    """Raised when product has insufficient quantity for withdrawal."""

    def __init__(self, sku: str, requested: int, available: int):
        self.sku = sku
        self.requested = requested
        self.available = available
        super().__init__(f"Insufficient stock for {sku}: requested {requested}, available {available}")
