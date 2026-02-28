"""SKU counter repository."""
from db import get_connection


async def get_next_number(department_code: str) -> int:
    """Return the next counter value without incrementing (for preview)."""
    conn = get_connection()
    cursor = await conn.execute(
        "SELECT counter FROM sku_counters WHERE department_code = ?",
        (department_code.upper(),),
    )
    row = await cursor.fetchone()
    return (row[0] + 1) if row else 1


async def get_all_counters() -> dict:
    """Return {department_code: counter} for all departments with counters."""
    conn = get_connection()
    cursor = await conn.execute(
        "SELECT department_code, counter FROM sku_counters"
    )
    rows = await cursor.fetchall()
    return {row[0]: row[1] for row in rows} if rows else {}


async def increment_and_get(department_code: str) -> int:
    conn = get_connection()
    await conn.execute(
        """INSERT INTO sku_counters (department_code, counter) VALUES (?, 1)
           ON CONFLICT(department_code) DO UPDATE SET counter = counter + 1""",
        (department_code,),
    )
    cursor = await conn.execute(
        "SELECT counter FROM sku_counters WHERE department_code = ?",
        (department_code,),
    )
    row = await cursor.fetchone()
    await conn.commit()
    return row[0] if row else 1


class SkuRepo:
    get_next_number = staticmethod(get_next_number)
    get_all_counters = staticmethod(get_all_counters)
    increment_and_get = staticmethod(increment_and_get)


sku_repo = SkuRepo()
