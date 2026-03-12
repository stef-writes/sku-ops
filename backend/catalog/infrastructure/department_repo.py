"""Department repository."""

from datetime import UTC, datetime

from catalog.domain.department import Department
from shared.infrastructure.database import get_connection, get_org_id


def _row_to_model(row) -> Department | None:
    if row is None:
        return None
    d = dict(row) if hasattr(row, "keys") else {}
    if not d:
        return None
    if d.get("organization_id") is None:
        d.pop("organization_id", None)
    return Department.model_validate(d)


async def list_all() -> list[Department]:
    conn = get_connection()
    org_id = get_org_id()
    cursor = await conn.execute(
        """SELECT id, name, code, description, product_count, organization_id, created_at FROM departments
           WHERE (organization_id = ? OR organization_id IS NULL) AND deleted_at IS NULL""",
        (org_id,),
    )
    rows = await cursor.fetchall()
    return [d for r in rows if (d := _row_to_model(r)) is not None]


async def get_by_id(dept_id: str) -> Department | None:
    conn = get_connection()
    org_id = get_org_id()
    cursor = await conn.execute(
        """SELECT id, name, code, description, product_count, organization_id, created_at FROM departments
           WHERE id = ? AND (organization_id = ? OR organization_id IS NULL) AND deleted_at IS NULL""",
        (dept_id, org_id),
    )
    row = await cursor.fetchone()
    return _row_to_model(row)


async def get_by_code(code: str) -> Department | None:
    conn = get_connection()
    org_id = get_org_id()
    cursor = await conn.execute(
        """SELECT id, name, code, description, product_count, organization_id, created_at FROM departments
           WHERE code = ? AND (organization_id = ? OR organization_id IS NULL) AND deleted_at IS NULL""",
        (code.upper(), org_id),
    )
    row = await cursor.fetchone()
    return _row_to_model(row)


async def insert(department: Department | dict) -> None:
    dept_dict = department if isinstance(department, dict) else department.model_dump()
    dept_dict["organization_id"] = dept_dict.get("organization_id") or get_org_id()
    conn = get_connection()
    org_id = dept_dict["organization_id"]
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


async def update(
    dept_id: str, name: str, description: str
) -> Department | None:
    conn = get_connection()
    org_id = get_org_id()
    params: list = [name, description or "", dept_id]
    where = "WHERE id = ? AND organization_id = ?"
    params.append(org_id)
    query = "UPDATE departments SET name = ?, description = ? "
    query += where
    await conn.execute(query, params)
    await conn.execute(
        "UPDATE products SET department_name = ? WHERE department_id = ?",
        (name, dept_id),
    )
    await conn.commit()
    return await get_by_id(dept_id)


async def count_products_by_department(dept_id: str) -> int:
    conn = get_connection()
    org_id = get_org_id()
    params: list = [dept_id]
    where = "WHERE department_id = ? AND deleted_at IS NULL AND (organization_id = ? OR organization_id IS NULL)"
    params.append(org_id)
    query = "SELECT COUNT(*) FROM products "
    query += where
    cursor = await conn.execute(query, params)
    row = await cursor.fetchone()
    return row[0] if row else 0


async def delete(dept_id: str) -> int:
    conn = get_connection()
    org_id = get_org_id()
    now = datetime.now(UTC).isoformat()
    params: list = [now, dept_id]
    where = "WHERE id = ? AND deleted_at IS NULL AND organization_id = ?"
    params.append(org_id)
    query = "UPDATE departments SET deleted_at = ? "
    query += where
    cursor = await conn.execute(query, params)
    await conn.commit()
    return cursor.rowcount


async def increment_product_count(dept_id: str, delta: int) -> None:
    conn = get_connection()
    org_id = get_org_id()
    params: list = [delta, dept_id]
    where = "WHERE id = ? AND organization_id = ?"
    params.append(org_id)
    query = "UPDATE departments SET product_count = product_count + ? "
    query += where
    await conn.execute(query, params)
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
