"""Address repository — persistence for the address book.

Cross-cutting reference data used by billing entities, jobs, etc.
"""

from shared.infrastructure.database import get_connection, get_org_id


def _row_to_dict(row) -> dict | None:
    if row is None:
        return None
    return dict(row)


_COLUMNS = "id, label, line1, line2, city, state, postal_code, country, billing_entity_id, job_id, organization_id, created_at"


async def insert(address: dict) -> None:
    conn = get_connection()
    ins_q = "INSERT INTO addresses ("
    ins_q += _COLUMNS
    ins_q += ") VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)"
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


async def get_by_id(address_id: str) -> dict | None:
    org_id = get_org_id()
    conn = get_connection()
    sel_q = "SELECT "
    sel_q += _COLUMNS
    sel_q += " FROM addresses WHERE id = $1 AND organization_id = $2"
    cursor = await conn.execute(sel_q, (address_id, org_id))
    return _row_to_dict(await cursor.fetchone())


async def list_addresses(
    billing_entity_id: str | None = None,
    job_id: str | None = None,
    q: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list:
    org_id = get_org_id()
    conn = get_connection()
    sql = "SELECT "
    sql += _COLUMNS
    sql += " FROM addresses WHERE organization_id = $1"
    params: list = [org_id]
    n = 2
    if billing_entity_id:
        sql += f" AND billing_entity_id = ${n}"
        params.append(billing_entity_id)
        n += 1
    if job_id:
        sql += f" AND job_id = ${n}"
        params.append(job_id)
        n += 1
    if q:
        like = f"%{q.lower()}%"
        sql += f" AND (LOWER(label) LIKE ${n} OR LOWER(line1) LIKE ${n + 1} OR LOWER(city) LIKE ${n + 2})"
        params.extend([like, like, like])
        n += 3
    sql += f" ORDER BY label, line1 LIMIT ${n} OFFSET ${n + 1}"
    params.extend([limit, offset])
    cursor = await conn.execute(sql, params)
    return [_row_to_dict(r) for r in await cursor.fetchall()]


async def search(query: str, limit: int = 20) -> list:
    """Fast prefix/substring search for autocomplete."""
    org_id = get_org_id()
    conn = get_connection()
    like = f"%{query.lower()}%"
    sel_q = "SELECT "
    sel_q += _COLUMNS
    sel_q += (
        " FROM addresses"
        " WHERE organization_id = $1"
        " AND (LOWER(label) LIKE $2 OR LOWER(line1) LIKE $3 OR LOWER(city) LIKE $4)"
        " ORDER BY label, line1 LIMIT $5"
    )
    cursor = await conn.execute(sel_q, (org_id, like, like, like, limit))
    return [_row_to_dict(r) for r in await cursor.fetchall()]


class AddressRepo:
    insert = staticmethod(insert)
    get_by_id = staticmethod(get_by_id)
    list_addresses = staticmethod(list_addresses)
    search = staticmethod(search)


address_repo = AddressRepo()
