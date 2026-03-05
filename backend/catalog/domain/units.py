"""Units of measure: allowed set, family groupings, and conversion logic."""

ALLOWED_BASE_UNITS: frozenset[str] = frozenset({
    "each", "case", "box", "pack", "bag", "roll", "kit",
    "gallon", "quart", "pint", "liter",
    "pound", "ounce",
    "foot", "inch", "meter", "yard",
    "sqft",
})

# Each family maps unit → factor relative to the smallest unit in that family.
UNIT_FAMILIES: dict[str, dict[str, float]] = {
    "length": {
        "inch":  1.0,
        "foot":  12.0,
        "yard":  36.0,
        "meter": 39.3701,
    },
    "volume": {
        "pint":   1.0,
        "quart":  2.0,
        "gallon": 8.0,
        "liter":  2.11338,
    },
    "weight": {
        "ounce": 1.0,
        "pound": 16.0,
    },
    "area": {
        "sqft": 1.0,
    },
    "discrete": {
        "each": 1.0,
        "pack": 1.0,
        "box":  1.0,
        "case": 1.0,
        "bag":  1.0,
        "roll": 1.0,
        "kit":  1.0,
    },
}

_UNIT_TO_FAMILY: dict[str, str] = {
    unit: family
    for family, units in UNIT_FAMILIES.items()
    for unit in units
}


def family_for_unit(unit: str) -> str | None:
    """Return the family name for a unit, or None if unknown."""
    return _UNIT_TO_FAMILY.get(unit.lower())


def convert_quantity(qty: float, from_unit: str, to_unit: str) -> float:
    """Convert qty between two units in the same family.

    Raises ValueError if the units belong to different families or are unknown.
    Returns qty unchanged if from_unit == to_unit.
    """
    from_unit = from_unit.lower()
    to_unit = to_unit.lower()
    if from_unit == to_unit:
        return qty

    from_family = _UNIT_TO_FAMILY.get(from_unit)
    to_family = _UNIT_TO_FAMILY.get(to_unit)

    if from_family is None:
        raise ValueError(f"Unknown unit: {from_unit}")
    if to_family is None:
        raise ValueError(f"Unknown unit: {to_unit}")
    if from_family != to_family:
        raise ValueError(
            f"Cannot convert between {from_unit} ({from_family}) "
            f"and {to_unit} ({to_family})"
        )

    from_factor = UNIT_FAMILIES[from_family][from_unit]
    to_factor = UNIT_FAMILIES[to_family][to_unit]
    return round(qty * from_factor / to_factor, 6)


def are_compatible(unit_a: str, unit_b: str) -> bool:
    """True if two units belong to the same family (convertible)."""
    fa = _UNIT_TO_FAMILY.get(unit_a.lower())
    fb = _UNIT_TO_FAMILY.get(unit_b.lower())
    return fa is not None and fa == fb
