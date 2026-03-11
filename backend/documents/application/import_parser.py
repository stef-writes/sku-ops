"""
Document import helpers: UOM resolution, department suggestion, CSV parsing.
Used by document import, CSV import, and seed flows.
"""

import contextlib
import csv
import io
import re

from shared.kernel.units import ALLOWED_BASE_UNITS


def resolve_uom(item: dict) -> tuple[str, str, int]:
    """Resolve base_unit, sell_uom, pack_qty from item, validating against allowed units."""
    bu = (item.get("base_unit") or "each").lower().strip()
    su = (item.get("sell_uom") or item.get("base_unit") or "each").lower().strip()
    pq = item.get("pack_qty")
    try:
        pq = max(1, int(pq)) if pq is not None else 1
    except (ValueError, TypeError):
        pq = 1
    bu = bu if bu in ALLOWED_BASE_UNITS else "each"
    su = su if su in ALLOWED_BASE_UNITS else "each"
    return bu, su, pq


# Keyword hints for auto-department from product name (Supply Yard style)
_DEPT_KEYWORDS = {
    "PLU": [
        "pex",
        "pvc",
        "cpvc",
        "pipe",
        "valve",
        "elbow",
        "coupling",
        "adapter",
        "sweat",
        "press",
        "crimp",
        "tailpiece",
        "drain",
        "faucet",
        "toilet",
        "sink",
    ],
    "ELE": [
        "wire",
        "cable",
        "connector",
        "emt",
        "conduit",
        "outlet",
        "switch",
        "breaker",
        "led",
        "light",
        "lamp",
        "box",
        "strap",
        "clamp",
        "knockout",
    ],
    "PNT": [
        "paint",
        "brush",
        "roller",
        "stain",
        "primer",
        "caulk",
        "spray",
        "sanding",
        "sandpaper",
    ],
    "LUM": [
        "lumber",
        "board",
        "stud",
        "plywood",
        "2x4",
        "2x6",
        "trim",
        "furring",
        "door",
        "slab",
        "moulding",
    ],
    "TOL": [
        "tool",
        "drill",
        "saw",
        "sander",
        "bit",
        "blade",
        "hammer",
        "screwdriver",
        "wrench",
        "level",
    ],
    "HDW": ["screw", "nail", "bolt", "anchor", "hinge", "lock", "bracket", "fastener"],
    "GDN": ["garden", "plant", "soil", "fertilizer", "hose", "sprinkler"],
    "APP": ["appliance", "furnace", "range", "hood", "filter", "hvac"],
}


def suggest_department(name: str, departments_by_code: dict) -> str | None:
    """Suggest department code from product name using keyword matching."""
    if not name:
        return None
    name_lower = name.lower()
    for code, keywords in _DEPT_KEYWORDS.items():
        if code in departments_by_code and any(kw in name_lower for kw in keywords):
            return code
    return None


def infer_uom(name: str) -> tuple[str, str, int]:
    """
    Infer base_unit, sell_uom, pack_qty from product name.
    Order: explicit patterns first (e.g. 5 gal), then keyword-based rules.
    """
    n = name.lower()

    # 1. Explicit quantity + unit patterns
    for pattern, unit in [
        (r"(\d+)\s*gal", "gallon"),
        (r"(\d+)\s*gal\.?", "gallon"),
        (r"gal(?:lon)?\b", "gallon"),
        (r"(\d+)\s*qt\.?", "quart"),
        (r"quart\b", "quart"),
        (r"(\d+)\s*pt\.?", "pint"),
        (r"(\d+)\s*pk\b", "pack"),
        (r"(\d+)pk\b", "pack"),
        (r"(\d+)\s*pack", "pack"),
        (r"(\d+)\s*box", "box"),
        (r"(\d+)\s*roll", "roll"),
        (r"(\d+)\s*case", "case"),
        (r"(\d+)\s*lb", "pound"),
        (r"(\d+)\s*oz", "ounce"),
        (r"(\d+)\s*ft\b", "foot"),
        (r"(\d+)\s*'\s*", "foot"),
        (r"(\d+)'\s*", "foot"),
        (r"x(\d+)'", "foot"),
        (r"(\d+)\s*lf\b", "foot"),
        (r"(\d+)\s*ln\s*ft", "foot"),
        (r'(\d+)\s*(?:in\b|in\.|")', "inch"),
        (r"(\d+)\s*inch", "inch"),
        (r"sq\s*ft", "sqft"),
        (r"(\d+)\s*sq\s*ft", "sqft"),
        (r"(\d+)\s*bag", "bag"),
        (r"(\d+)\s*kit", "kit"),
    ]:
        m = re.search(pattern, n, re.IGNORECASE)
        if m and unit in ALLOWED_BASE_UNITS:
            pq = 1
            if m.groups() and m.group(1):
                with contextlib.suppress(ValueError, TypeError):
                    pq = max(1, int(m.group(1)))
            return unit, unit, pq

    # 2. Roll (before linear - tape, mesh are roll not foot)
    roll_keywords = ["tape", "screen", "mesh", "landscape fabric", "vapor barrier", "house wrap"]
    if any(kw in n for kw in roll_keywords):
        return "roll", "roll", 1

    # 3. Keyword-based inference (linear / by foot)
    linear_keywords = [
        "pipe",
        "pvc",
        "cpvc",
        "pex",
        "conduit",
        "emt",
        "wire",
        "cable",
        "romex",
        "rope",
        "hose",
        "chain",
        "cord",
        "extension cord",
        "trim",
        "moulding",
        "molding",
        "lumber",
        "stud",
        "2x4",
        "2x6",
        "2x8",
        "1x4",
        "1x6",
        "board",
        "furring",
        "rebar",
        "angle iron",
        "duct",
        "ductwork",
        "flex duct",
        "b vent",
        "sill plate",
        "joist",
        "rafter",
        "siding",
        "fencing",
        "fence",
    ]
    if any(kw in n for kw in linear_keywords):
        # Extract length if present (e.g. "2x4x8" -> 8, "100ft" -> 100)
        len_matches = re.findall(r"(?:x|\*)(\d+)\b", n)
        pq = max(1, int(len_matches[-1])) if len_matches else 1
        ft_m = re.search(r"(\d+)\s*ft\b", n) or re.search(r"(\d+)\s*'\s*", n)
        if ft_m:
            pq = max(1, int(ft_m.group(1)))
        return "foot", "foot", pq

    # 3. Liquid / coatings
    liquid_keywords = ["paint", "stain", "primer", "sealer", "thinner", "polyurethane", "varnish"]
    if any(kw in n for kw in liquid_keywords):
        if "quart" in n or "qt" in n:
            return "quart", "quart", 1
        if "pint" in n or "pt" in n:
            return "pint", "pint", 1
        return "gallon", "gallon", 1

    # 5. Box / pack (fasteners, small parts)
    box_keywords = [
        "screw",
        "nail",
        "bolt",
        "nut",
        "washer",
        "anchor",
        "fastener",
        "rivet",
        "staple",
    ]
    if any(kw in n for kw in box_keywords):
        if "box" in n or "bx" in n:
            return "box", "box", 1
        if "pack" in n or "pk" in n or "pkg" in n:
            return "pack", "pack", 1
        if "case" in n:
            return "case", "case", 1
        return "box", "box", 1

    # 6. Sqft (sheet goods)
    sqft_keywords = [
        "drywall",
        "sheetrock",
        "plywood",
        "osb",
        "mdf",
        "hardboard",
        "insulation board",
        "ceiling tile",
    ]
    if any(kw in n for kw in sqft_keywords):
        return "sqft", "sqft", 1

    # 7. Bag (bulk) - concrete, soil, etc
    bag_keywords = ["concrete", "mortar", "grout", "sand", "gravel", "mulch", "soil", "fertilizer"]
    if any(kw in n for kw in bag_keywords):
        if "lb" in n or "pound" in n:
            return "pound", "pound", 1
        return "bag", "bag", 1

    # 8. Kit / each (assemblies, fixtures)
    kit_keywords = ["kit", "assembly", "faucet", "light fixture", "vanity", "toilet", "sink"]
    if any(kw in n for kw in kit_keywords):
        if "kit" in n:
            return "kit", "kit", 1
        return "each", "each", 1

    return "each", "each", 1


def parse_dollar(val: str) -> float:
    """Parse '$2.73' or '2.73' to float."""
    if not val or not str(val).strip():
        return 0.0
    s = str(val).replace("$", "").replace(",", "").strip()
    try:
        return round(float(s), 2)
    except (ValueError, TypeError):
        return 0.0


def parse_csv_products(content: bytes) -> list:
    """
    Parse Supply Yard inventory CSV format.
    Columns: Product, SKU, Barcode, On hand, Reorder qty, Reorder point,
             Unit cost, Total cost, Retail price, Retail (Ex. Tax), Retail (Inc. Tax), Department/Category
    """
    decoded = content.decode("utf-8", errors="replace")
    reader = csv.reader(io.StringIO(decoded))

    header = None
    header_idx = -1
    for i, row in enumerate(reader):
        if row and str(row[0]).strip().lower() == "product":
            header = [c.strip() for c in row]
            header_idx = i
            break

    if not header:
        raise ValueError("CSV must have a header row with 'Product' in first column")

    col_map = {}
    for idx, name in enumerate(header):
        n = name.lower()
        if "product" in n:
            col_map["name"] = idx
        elif "sku" in n and "barcode" not in n:
            col_map["sku"] = idx
        elif "on hand" in n or "quantity" in n:
            col_map["quantity"] = idx
        elif "reorder point" in n:
            col_map["min_stock"] = idx
        elif "unit cost" in n or ("cost" in n and "total" not in n and "cost" not in col_map):
            col_map["cost"] = idx
        elif "retail price" in n and "ex" not in n and "inc" not in n:
            col_map["price"] = idx
        elif "department" in n or "category" in n:
            col_map["department"] = idx
        elif "barcode" in n:
            col_map["barcode"] = idx

    if "name" not in col_map:
        raise ValueError("CSV must have a Product/name column")

    decoded2 = content.decode("utf-8", errors="replace")
    rows = list(csv.reader(io.StringIO(decoded2)))

    products = []
    for i, row in enumerate(rows):
        if i <= header_idx or len(row) <= col_map["name"]:
            continue
        name = (row[col_map["name"]] or "").strip()
        if not name:
            continue
        if name.lower().startswith("current inventory") or name.lower().startswith(
            "for the period"
        ):
            continue

        qty = 0.0
        with contextlib.suppress(ValueError, TypeError, IndexError):
            qty = float((row[col_map.get("quantity", 3)] or "0").replace(",", ""))

        cost = parse_dollar(
            row[col_map.get("cost", 6)] if col_map.get("cost", 6) < len(row) else "0"
        )
        price = parse_dollar(
            row[col_map.get("price", 8)] if col_map.get("price", 8) < len(row) else "0"
        )
        if price <= 0 and cost > 0:
            price = round(cost * 1.4, 2)
        elif cost <= 0 and price > 0:
            cost = round(price * 0.7, 2)

        min_stock = 5
        with contextlib.suppress(ValueError, TypeError, IndexError):
            min_stock = max(
                0, int(float((row[col_map.get("min_stock", 5)] or "0").replace(",", "")))
            )
        if min_stock == 0:
            min_stock = 5

        products.append(
            {
                "name": name,
                "quantity": qty,
                "cost": cost,
                "price": price,
                "min_stock": min_stock,
                "original_sku": (row[col_map["sku"]] or "").strip() or None
                if col_map.get("sku") is not None and col_map["sku"] < len(row)
                else None,
                "barcode": (row[col_map["barcode"]] or "").strip() or None
                if col_map.get("barcode") is not None and col_map["barcode"] < len(row)
                else None,
                "department": (row[col_map["department"]] or "").strip() or None
                if col_map.get("department") is not None and col_map["department"] < len(row)
                else None,
            }
        )

    return products
