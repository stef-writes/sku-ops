"""Department repository."""
from typing import Optional

from shared.infrastructure.database import get_connection


def _row_to_dict(row) -> Optional[dict]:
    if row is None:
        return None
    return dict(row) if hasattr(row, "keys") else {}


async def list_all(organization_id: Optional[str] = None) -> list:
    conn = get_connection()
    org_id = organization_id or "default"
    cursor = await conn.execute(
        """SELECT id, name, code, description, product_count, organization_id, created_at FROM departments
           WHERE organization_id = ? OR organization_id IS NULL""",
        (org_id,),
    )
    rows = await cursor.fetchall()
    return [_row_to_dict(r) for r in rows]


async def get_by_id(dept_id: str, organization_id: Optional[str] = None) -> Optional[dict]:
    conn = get_connection()
    if organization_id:
        cursor = await conn.execute(
            """SELECT id, name, code, description, product_count, organization_id, created_at FROM departments
               WHERE id = ? AND (organization_id = ? OR organization_id IS NULL)""",
            (dept_id, organization_id),
        )
    else:
        cursor = await conn.execute(
            "SELECT id, name, code, description, product_count, organization_id, created_at FROM departments WHERE id = ?",
            (dept_id,),
        )
    row = await cursor.fetchone()
    return _row_to_dict(row)


async def get_by_code(code: str, organization_id: Optional[str] = None) -> Optional[dict]:
    conn = get_connection()
    org_id = organization_id or "default"
    cursor = await conn.execute(
        """SELECT id, name, code, description, product_count, organization_id, created_at FROM departments
           WHERE code = ? AND (organization_id = ? OR organization_id IS NULL)""",
        (code.upper(), org_id),
    )
    row = await cursor.fetchone()
    return _row_to_dict(row)


async def insert(dept_dict: dict) -> None:
    conn = get_connection()
    org_id = dept_dict.get("organization_id") or "default"
    await conn.execute(
        """INSERT INTO departments (id, name, code, description, product_count, organization_id, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            dept_dict["id"],
            dept_dict["name"],
            dept_dict["code"].upper(),
            dept_dict.get("description", ""),
            dept_dict.get("product_count", 0),
            org_id,
            dept_dict.get("created_at", ""),
        ),
    )
    await conn.commit()


async def update(dept_id: str, name: str, description: str, conn=None) -> Optional[dict]:
    in_transaction = conn is not None
    conn = conn or get_connection()
    await conn.execute(
        "UPDATE departments SET name = ?, description = ? WHERE id = ?",
        (name, description or "", dept_id),
    )
    await conn.execute(
        "UPDATE products SET department_name = ? WHERE department_id = ?",
        (name, dept_id),
    )
    if not in_transaction:
        await conn.commit()
    return await get_by_id(dept_id)


async def count_products_by_department(dept_id: str) -> int:
    conn = get_connection()
    cursor = await conn.execute(
        "SELECT COUNT(*) FROM products WHERE department_id = ?",
        (dept_id,),
    )
    row = await cursor.fetchone()
    return row[0] if row else 0


async def delete(dept_id: str) -> int:
    conn = get_connection()
    cursor = await conn.execute("DELETE FROM departments WHERE id = ?", (dept_id,))
    await conn.commit()
    return cursor.rowcount


async def increment_product_count(dept_id: str, delta: int, conn=None) -> None:
    in_transaction = conn is not None
    conn = conn or get_connection()
    await conn.execute(
        "UPDATE departments SET product_count = product_count + ? WHERE id = ?",
        (delta, dept_id),
    )
    if not in_transaction:
        await conn.commit()


class DepartmentRepo:
    list_all = staticmethod(list_all)
    get_by_id = staticmethod(get_by_id)
    get_by_code = staticmethod(get_by_code)
    insert = staticmethod(insert)
    update = staticmethod(update)
    count_products_by_department = staticmethod(count_products_by_department)
    delete = staticmethod(delete)
    increment_product_count = staticmethod(increment_product_count)


department_repo = DepartmentRepo()
