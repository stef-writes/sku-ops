"""Department repository."""

from datetime import UTC, datetime

from catalog.domain.department import Department
from shared.infrastructure.database import get_connection, get_org_id


def _row_to_model(row) -> Department | None:
    if row is None:
        return None
    d = dict(row)
    if d.get("organization_id") is None:
        d.pop("organization_id", None)
    return Department.model_validate(d)


async def list_all() -> list[Department]:
    conn = get_connection()
    org_id = get_org_id()
    cursor = await conn.execute(
        """SELECT id, name, code, description, sku_count, organization_id, created_at FROM departments
           WHERE (organization_id = $1 OR organization_id IS NULL) AND deleted_at IS NULL""",
        (org_id,),
    )
    rows = await cursor.fetchall()
    return [d for r in rows if (d := _row_to_model(r)) is not None]


async def get_by_id(dept_id: str) -> Department | None:
    conn = get_connection()
    org_id = get_org_id()
    cursor = await conn.execute(
        """SELECT id, name, code, description, sku_count, organization_id, created_at FROM departments
           WHERE id = $1 AND (organization_id = $2 OR organization_id IS NULL) AND deleted_at IS NULL""",
        (dept_id, org_id),
    )
    row = await cursor.fetchone()
    return _row_to_model(row)


async def get_by_code(code: str) -> Department | None:
    conn = get_connection()
    org_id = get_org_id()
    cursor = await conn.execute(
        """SELECT id, name, code, description, sku_count, organization_id, created_at FROM departments
           WHERE code = $1 AND (organization_id = $2 OR organization_id IS NULL) AND deleted_at IS NULL""",
        (code.upper(), org_id),
    )
    row = await cursor.fetchone()
    return _row_to_model(row)


async def insert(department: Department) -> None:
    dept_dict = department.model_dump()
    dept_dict["organization_id"] = dept_dict.get("organization_id") or get_org_id()
    conn = get_connection()
    org_id = dept_dict["organization_id"]
    await conn.execute(
        """INSERT INTO departments (id, name, code, description, sku_count, organization_id, created_at)
           VALUES ($1, $2, $3, $4, $5, $6, $7)""",
        (
            dept_dict["id"],
            dept_dict["name"],
            dept_dict["code"].upper(),
            dept_dict.get("description", ""),
            dept_dict.get("sku_count", 0),
            org_id,
            dept_dict.get("created_at", ""),
        ),
    )
    await conn.commit()


async def update(dept_id: str, name: str, description: str) -> Department | None:
    conn = get_connection()
    org_id = get_org_id()
    params: list = [name, description or "", dept_id]
    where = "WHERE id = $3 AND organization_id = $4"
    params.append(org_id)
    query = "UPDATE departments SET name = $1, description = $2 "
    query += where
    await conn.execute(query, params)
    await conn.execute(
        "UPDATE skus SET category_name = $1 WHERE category_id = $2",
        (name, dept_id),
    )
    await conn.execute(
        "UPDATE products SET category_name = $1 WHERE category_id = $2",
        (name, dept_id),
    )
    await conn.commit()
    return await get_by_id(dept_id)


async def count_skus_by_department(dept_id: str) -> int:
    conn = get_connection()
    org_id = get_org_id()
    cursor = await conn.execute(
        "SELECT COUNT(*) FROM skus WHERE category_id = $1 AND deleted_at IS NULL AND (organization_id = $2 OR organization_id IS NULL)",
        (dept_id, org_id),
    )
    row = await cursor.fetchone()
    return row[0] if row else 0


async def delete(dept_id: str) -> int:
    conn = get_connection()
    org_id = get_org_id()
    now = datetime.now(UTC).isoformat()
    params: list = [now, dept_id]
    where = "WHERE id = $2 AND deleted_at IS NULL AND organization_id = $3"
    params.append(org_id)
    query = "UPDATE departments SET deleted_at = $1 "
    query += where
    cursor = await conn.execute(query, params)
    await conn.commit()
    return cursor.rowcount


async def increment_sku_count(dept_id: str, delta: int) -> None:
    conn = get_connection()
    org_id = get_org_id()
    params: list = [delta, dept_id]
    where = "WHERE id = $2 AND organization_id = $3"
    params.append(org_id)
    query = "UPDATE departments SET sku_count = sku_count + $1 "
    query += where
    await conn.execute(query, params)
    await conn.commit()


class DepartmentRepo:
    list_all = staticmethod(list_all)
    get_by_id = staticmethod(get_by_id)
    get_by_code = staticmethod(get_by_code)
    insert = staticmethod(insert)
    update = staticmethod(update)
    count_skus_by_department = staticmethod(count_skus_by_department)
    delete = staticmethod(delete)
    increment_sku_count = staticmethod(increment_sku_count)


department_repo = DepartmentRepo()
