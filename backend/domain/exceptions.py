"""Domain exceptions - no HTTP coupling. Map to HTTP in API layer."""


class InsufficientStockError(Exception):
    """Raised when product has insufficient quantity for withdrawal."""

    def __init__(self, sku: str, requested: int, available: int):
        self.sku = sku
        self.requested = requested
        self.available = available
        super().__init__(f"Insufficient stock for {sku}: requested {requested}, available {available}")


class ResourceNotFoundError(Exception):
    """Raised when a required resource (product, department, etc.) is not found."""

    def __init__(self, resource_type: str, resource_id: str):
        self.resource_type = resource_type
        self.resource_id = resource_id
        super().__init__(f"{resource_type} not found: {resource_id}")


class DuplicateBarcodeError(Exception):
    """Raised when barcode is already used by another product."""

    def __init__(self, barcode: str, product_name: str):
        self.barcode = barcode
        self.product_name = product_name
        super().__init__(f"Barcode already used by product: {product_name}")


class InvalidBarcodeError(Exception):
    """Raised when barcode fails validation (e.g. invalid UPC check digit)."""

    def __init__(self, barcode: str, reason: str):
        self.barcode = barcode
        self.reason = reason
        super().__init__(f"Invalid barcode: {reason}")
