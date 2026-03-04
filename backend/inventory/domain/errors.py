"""Inventory-specific domain errors."""
from kernel.errors import DomainError


class InsufficientStockError(DomainError):
    """Raised when product has insufficient quantity for withdrawal."""

    def __init__(self, sku: str, requested: int, available: int):
        self.sku = sku
        self.requested = requested
        self.available = available
        super().__init__(f"Insufficient stock for {sku}: requested {requested}, available {available}")


class NegativeStockError(DomainError):
    """Raised when a stock adjustment would result in negative quantity."""

    def __init__(self, product_id: str, current: int, delta: int):
        self.product_id = product_id
        self.current = current
        self.delta = delta
        super().__init__(
            f"Cannot adjust: would result in negative stock "
            f"(current: {current}, delta: {delta})"
        )
