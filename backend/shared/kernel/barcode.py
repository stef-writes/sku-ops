"""
Barcode validation - UPC-A, EAN-13, and generic formats.
Industry standard check digit validation for numeric barcodes.
"""


def _upc_check_digit(first_11: str) -> int:
    """Compute UPC-A check digit from first 11 digits. Positions 1,3,5,7,9,11 ×3; 2,4,6,8,10 ×1."""
    total = 0
    for i, d in enumerate(first_11[:11]):
        digit = int(d)
        if (i + 1) % 2 == 1:  # odd position (1-based)
            total += digit * 3
        else:
            total += digit
    check = (10 - (total % 10)) % 10
    return check


def _ean13_check_digit(first_12: str) -> int:
    """Compute EAN-13 check digit. Odd positions ×1, even ×3."""
    total = 0
    for i, d in enumerate(first_12[:12]):
        digit = int(d)
        if (i + 1) % 2 == 1:  # odd position
            total += digit
        else:
            total += digit * 3
    check = (10 - (total % 10)) % 10
    return check


def validate_upc(value: str) -> bool:
    """Validate UPC-A (12 digits) including check digit. Returns True if valid."""
    if not value or not isinstance(value, str):
        return False
    s = value.strip()
    if len(s) != 12 or not s.isdigit():
        return False
    expected = _upc_check_digit(s[:11])
    return int(s[11]) == expected


def validate_ean13(value: str) -> bool:
    """Validate EAN-13 (13 digits) including check digit. Returns True if valid."""
    if not value or not isinstance(value, str):
        return False
    s = value.strip()
    if len(s) != 13 or not s.isdigit():
        return False
    expected = _ean13_check_digit(s[:12])
    return int(s[12]) == expected


def validate_barcode(value: str) -> tuple[bool, str | None]:
    """Validate barcode and return (valid, format).

    - 12 digits + valid UPC check digit → (True, "UPC")
    - 13 digits + valid EAN-13 check digit → (True, "EAN13")
    - Alphanumeric (SKU, internal codes) → (True, "CODE128") — no check digit required
    - Invalid → (False, None)
    """
    if not value or not isinstance(value, str):
        return False, None
    s = value.strip()
    if not s:
        return False, None

    if s.isdigit():
        if len(s) == 12:
            return (True, "UPC") if validate_upc(s) else (False, None)
        if len(s) == 13:
            return (True, "EAN13") if validate_ean13(s) else (False, None)
        return False, None

    # Alphanumeric — e.g. SKU like LUM-PIPE-000001
    return True, "CODE128"
