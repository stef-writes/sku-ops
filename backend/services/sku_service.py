"""
SKU generation service.
"""
from typing import Optional

from repositories import sku_repo
from services.sku_slug import slug_from_name


async def generate_sku(department_code: str, product_name: Optional[str] = None) -> str:
    """Generate SKU: DEPT-SLUG-00001. Slug derived from product name for readability."""
    number = await sku_repo.increment_and_get(department_code)
    slug = slug_from_name(product_name or "", max_len=6) if product_name else "ITM"
    return f"{department_code}-{slug}-{str(number).zfill(6)}"
