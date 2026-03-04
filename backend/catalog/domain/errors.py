"""Catalog-specific domain errors."""
from kernel.errors import DomainError


class DuplicateBarcodeError(DomainError):
    """Raised when barcode is already used by another product."""
    status_hint = 409

    def __init__(self, barcode: str, product_name: str):
        self.barcode = barcode
        self.product_name = product_name
        super().__init__(f"Barcode already used by product: {product_name}")


class InvalidBarcodeError(DomainError):
    """Raised when barcode fails validation (e.g. invalid UPC check digit)."""

    def __init__(self, barcode: str, reason: str):
        self.barcode = barcode
        self.reason = reason
        super().__init__(f"Invalid barcode: {reason}")
