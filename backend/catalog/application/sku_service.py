"""SKU generation — slug derivation and sequential counter management."""

import re

from catalog.application import queries as catalog_queries
from catalog.infrastructure.sku_repo import sku_repo
from shared.kernel.errors import ResourceNotFoundError

SKU_FORMAT = "DEPT-SLUG-XXXXX"
_DEFAULT_SLUG = "ITM"


def slug_from_name(name: str, max_len: int = 6) -> str:
    """Derive a short alphanumeric slug from product name (e.g. 'copper pipe' → 'COPPER').

    Uppercase, alphanumeric only, truncated to max_len.
    """
    if not name or not str(name).strip():
        return _DEFAULT_SLUG
    s = str(name).strip().upper()
    s = re.sub(r"[^A-Z0-9]", "", s)
    if not s:
        return _DEFAULT_SLUG
    return s[:max_len] if len(s) > max_len else s


async def generate_sku(
    department_code: str,
    product_name: str | None = None,
) -> str:
    """Generate SKU: DEPT-SLUG-000001. Slug derived from product name for readability."""
    number = await sku_repo.increment_and_get(department_code)
    slug = slug_from_name(product_name or "", max_len=6) if product_name else _DEFAULT_SLUG
    return f"{department_code}-{slug}-{str(number).zfill(6)}"


async def preview_sku(department_id: str, product_name: str | None = None) -> dict:
    """Preview the next SKU for a department without consuming the counter."""
    department = await catalog_queries.get_department_by_id(department_id)
    if not department:
        raise ResourceNotFoundError("Department", department_id)
    code = department.code
    next_num = await catalog_queries.get_next_sku_number(code)
    slug = slug_from_name(product_name or "", max_len=6) if product_name else _DEFAULT_SLUG
    return {
        "next_sku": f"{code}-{slug}-{str(next_num).zfill(6)}",
        "department_code": code,
        "format": SKU_FORMAT,
        "slug": slug,
    }


async def sku_overview(product_name: str | None = None) -> dict:
    """Return SKU format info and next available SKU for every department."""
    departments = await catalog_queries.list_departments()
    counters = await catalog_queries.get_sku_counters()
    slug = slug_from_name(product_name or "", max_len=6) if product_name else _DEFAULT_SLUG
    depts_with_next = []
    for d in departments:
        code = d.code
        next_num = counters.get(code, 0) + 1
        dept_data = d.model_dump()
        dept_data["next_sku"] = f"{code}-{slug}-{str(next_num).zfill(6)}"
        depts_with_next.append(dept_data)
    return {"format": SKU_FORMAT, "departments": depts_with_next}
