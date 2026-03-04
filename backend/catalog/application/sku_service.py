"""SKU generation — slug derivation and sequential counter management."""
import re
from typing import Optional

from catalog.infrastructure.sku_repo import sku_repo


def slug_from_name(name: str, max_len: int = 6) -> str:
    """Derive a short alphanumeric slug from product name (e.g. 'copper pipe' → 'COPPER').

    Uppercase, alphanumeric only, truncated to max_len.
    """
    if not name or not str(name).strip():
        return "ITM"
    s = str(name).strip().upper()
    s = re.sub(r"[^A-Z0-9]", "", s)
    if not s:
        return "ITM"
    return s[:max_len] if len(s) > max_len else s


async def generate_sku(
    department_code: str,
    product_name: Optional[str] = None,
    organization_id: Optional[str] = None,
) -> str:
    """Generate SKU: DEPT-SLUG-000001. Slug derived from product name for readability."""
    number = await sku_repo.increment_and_get(department_code, organization_id)
    slug = slug_from_name(product_name or "", max_len=6) if product_name else "ITM"
    return f"{department_code}-{slug}-{str(number).zfill(6)}"
