"""Address repository — persistence for the address book.

Cross-cutting reference data used by billing entities, jobs, etc.
"""

from shared.infrastructure.database import get_connection


def _row_to_dict(row) -> dict | None:
    if row is None:
        return None
    return dict(row) if hasattr(row, "keys") else {}


_COLUMNS = "id, label, line1, line2, city, state, postal_code, country, billing_entity_id, job_id, organization_id, created_at"


async def insert(address: dict) -> None:
    conn = get_connection()
    ins_q = "INSERT INTO addresses ("
    ins_q += _COLUMNS
    ins_q += ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    await conn.execute(
        ins_q,
        (
            address["id"],
            address.get("label", ""),
            address.get("line1", ""),
            address.get("line2", ""),
            address.get("city", ""),
            address.get("state", ""),
            address.get("postal_code", ""),
            address.get("country", "US"),
            address.get("billing_entity_id"),
            address.get("job_id"),
            address["organization_id"],
            address["created_at"],
        ),
    )
    await conn.commit()


async def get_by_id(address_id: str, organization_id: str) -> dict | None:
    conn = get_connection()
    sel_q = "SELECT "
    sel_q += _COLUMNS
    sel_q += " FROM addresses WHERE id = ? AND organization_id = ?"
    cursor = await conn.execute(sel_q, (address_id, organization_id))
    return _row_to_dict(await cursor.fetchone())


async def list_addresses(
    organization_id: str,
    billing_entity_id: str | None = None,
    job_id: str | None = None,
    q: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list:
    conn = get_connection()
    sql = "SELECT "
    sql += _COLUMNS
    sql += " FROM addresses WHERE organization_id = ?"
    params: list = [organization_id]
    if billing_entity_id:
        sql += " AND billing_entity_id = ?"
        params.append(billing_entity_id)
    if job_id:
        sql += " AND job_id = ?"
        params.append(job_id)
    if q:
        like = f"%{q.lower()}%"
        sql += " AND (LOWER(label) LIKE ? OR LOWER(line1) LIKE ? OR LOWER(city) LIKE ?)"
        params.extend([like, like, like])
    sql += " ORDER BY label, line1 LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    cursor = await conn.execute(sql, params)
    return [_row_to_dict(r) for r in await cursor.fetchall()]


async def search(query: str, organization_id: str, limit: int = 20) -> list:
    """Fast prefix/substring search for autocomplete."""
    conn = get_connection()
    like = f"%{query.lower()}%"
    sel_q = "SELECT "
    sel_q += _COLUMNS
    sel_q += (
        " FROM addresses"
        " WHERE organization_id = ?"
        " AND (LOWER(label) LIKE ? OR LOWER(line1) LIKE ? OR LOWER(city) LIKE ?)"
        " ORDER BY label, line1 LIMIT ?"
    )
    cursor = await conn.execute(sel_q, (organization_id, like, like, like, limit))
    return [_row_to_dict(r) for r in await cursor.fetchall()]


class AddressRepo:
    insert = staticmethod(insert)
    get_by_id = staticmethod(get_by_id)
    list_addresses = staticmethod(list_addresses)
    search = staticmethod(search)


address_repo = AddressRepo()
