"""Allowed units of measure for the product catalog."""

ALLOWED_BASE_UNITS: frozenset[str] = frozenset({
    "each", "case", "box", "pack", "bag", "roll", "kit",
    "gallon", "quart", "pint", "liter",
    "pound", "ounce",
    "foot", "meter", "yard",
    "sqft",
})
