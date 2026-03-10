"""SKU counter repository."""

from shared.infrastructure.config import DEFAULT_ORG_ID
from shared.infrastructure.database import get_connection


def _counter_key(organization_id: str | None, department_code: str) -> str:
    """Composite key for org-scoped SKU counters. Backward compat: use plain code if no org."""
    org = organization_id or DEFAULT_ORG_ID
    code = (department_code or "").strip().upper()
    return f"{org}|{code}"


async def get_next_number(department_code: str, organization_id: str | None = None) -> int:
    """Return the next counter value without incrementing (for preview)."""
    conn = get_connection()
    key = _counter_key(organization_id, department_code)
    cursor = await conn.execute(
        "SELECT counter FROM sku_counters WHERE department_code = ?",
        (key,),
    )
    row = await cursor.fetchone()
    return (row[0] + 1) if row else 1


async def get_all_counters(organization_id: str | None = None) -> dict:
    """Return {department_code: counter} for org's departments with counters."""
    conn = get_connection()
    prefix = f"{organization_id or 'default'}|"
    cursor = await conn.execute(
        "SELECT department_code, counter FROM sku_counters WHERE department_code LIKE ?",
        (f"{prefix}%",),
    )
    rows = await cursor.fetchall()
    # Strip org prefix for backward compat
    return {row[0].split("|", 1)[-1]: row[1] for row in rows} if rows else {}


async def increment_and_get(department_code: str, organization_id: str | None = None) -> int:
    code = (department_code or "").strip().upper()
    key = _counter_key(organization_id, code)
    conn = get_connection()
    await conn.execute(
        """INSERT INTO sku_counters (department_code, counter) VALUES (?, 1)
           ON CONFLICT(department_code) DO UPDATE SET counter = counter + 1""",
        (key,),
    )
    cursor = await conn.execute(
        "SELECT counter FROM sku_counters WHERE department_code = ?",
        (key,),
    )
    row = await cursor.fetchone()
    await conn.commit()
    return row[0] if row else 1


class SkuRepo:
    get_next_number = staticmethod(get_next_number)
    get_all_counters = staticmethod(get_all_counters)
    increment_and_get = staticmethod(increment_and_get)


sku_repo = SkuRepo()
