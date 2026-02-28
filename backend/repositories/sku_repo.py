"""SKU counter repository."""
from db import get_connection


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
    increment_and_get = staticmethod(increment_and_get)


sku_repo = SkuRepo()
