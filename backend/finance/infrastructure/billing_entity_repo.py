"""Billing entity repository — persistence for billing entity master data."""

from datetime import UTC, datetime

from finance.domain.billing_entity import BillingEntity
from shared.infrastructure.database import get_connection, get_org_id


def _row_to_model(row) -> BillingEntity | None:
    if row is None:
        return None
    d = dict(row)
    if "is_active" in d:
        d["is_active"] = bool(d["is_active"])
    return BillingEntity.model_validate(d)


_COLUMNS = "id, name, contact_name, contact_email, billing_address, payment_terms, xero_contact_id, is_active, organization_id, created_at, updated_at"


async def insert(entity: BillingEntity) -> None:
    d = entity.model_dump()
    conn = get_connection()
    ins_q = "INSERT INTO billing_entities ("
    ins_q += _COLUMNS
    ins_q += ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    await conn.execute(
        ins_q,
        (
            d["id"],
            d["name"],
            d.get("contact_name", ""),
            d.get("contact_email", ""),
            d.get("billing_address", ""),
            d.get("payment_terms", "net_30"),
            d.get("xero_contact_id"),
            1 if d.get("is_active", True) else 0,
            d["organization_id"],
            d["created_at"],
            d["updated_at"],
        ),
    )
    await conn.commit()


async def get_by_id(entity_id: str) -> BillingEntity | None:
    org_id = get_org_id()
    conn = get_connection()
    sel_q = "SELECT "
    sel_q += _COLUMNS
    sel_q += " FROM billing_entities WHERE id = ? AND organization_id = ?"
    cursor = await conn.execute(sel_q, (entity_id, org_id))
    return _row_to_model(await cursor.fetchone())


async def get_by_name(name: str) -> BillingEntity | None:
    org_id = get_org_id()
    conn = get_connection()
    sel_q = "SELECT "
    sel_q += _COLUMNS
    sel_q += " FROM billing_entities WHERE LOWER(TRIM(name)) = ? AND organization_id = ?"
    cursor = await conn.execute(sel_q, (name.strip().lower(), org_id))
    return _row_to_model(await cursor.fetchone())


async def list_billing_entities(
    is_active: bool | None = None,
    q: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list:
    org_id = get_org_id()
    conn = get_connection()
    sql = "SELECT "
    sql += _COLUMNS
    sql += " FROM billing_entities WHERE organization_id = ?"
    params: list = [org_id]
    if is_active is not None:
        sql += " AND is_active = ?"
        params.append(1 if is_active else 0)
    if q:
        sql += " AND (LOWER(name) LIKE ? OR LOWER(contact_name) LIKE ?)"
        like = f"%{q.lower()}%"
        params.extend([like, like])
    sql += " ORDER BY name LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    cursor = await conn.execute(sql, params)
    return [e for r in await cursor.fetchall() if (e := _row_to_model(r)) is not None]


async def update(entity_id: str, updates: dict) -> BillingEntity | None:
    org_id = get_org_id()
    conn = get_connection()
    set_clauses = []
    params = []
    for key in (
        "name",
        "contact_name",
        "contact_email",
        "billing_address",
        "payment_terms",
        "xero_contact_id",
    ):
        if key in updates and updates[key] is not None:
            set_clauses.append(f"{key} = ?")
            params.append(updates[key])
    if "is_active" in updates and updates["is_active"] is not None:
        set_clauses.append("is_active = ?")
        params.append(1 if updates["is_active"] else 0)
    if not set_clauses:
        return await get_by_id(entity_id)
    set_clauses.append("updated_at = ?")
    params.append(datetime.now(UTC).isoformat())
    params.extend([entity_id, org_id])
    upd_q = "UPDATE billing_entities SET "
    upd_q += ", ".join(set_clauses)
    upd_q += " WHERE id = ? AND organization_id = ?"
    await conn.execute(upd_q, params)
    await conn.commit()
    return await get_by_id(entity_id)


async def search(query: str, limit: int = 20) -> list:
    """Fast prefix/substring search for autocomplete."""
    org_id = get_org_id()
    conn = get_connection()
    like = f"%{query.lower()}%"
    sel_q = "SELECT "
    sel_q += _COLUMNS
    sel_q += (
        " FROM billing_entities"
        " WHERE organization_id = ? AND is_active = 1"
        " AND (LOWER(name) LIKE ? OR LOWER(contact_name) LIKE ?)"
        " ORDER BY name LIMIT ?"
    )
    cursor = await conn.execute(sel_q, (org_id, like, like, limit))
    return [e for r in await cursor.fetchall() if (e := _row_to_model(r)) is not None]


async def ensure_billing_entity(name: str) -> BillingEntity | None:
    """Get existing entity by name, or auto-create a minimal one."""
    if not name or not name.strip():
        return None
    org_id = get_org_id()
    existing = await get_by_name(name)
    if existing:
        return existing
    entity = BillingEntity(name=name.strip(), organization_id=org_id)
    await insert(entity)
    return entity


class BillingEntityRepo:
    insert = staticmethod(insert)
    get_by_id = staticmethod(get_by_id)
    get_by_name = staticmethod(get_by_name)
    list_billing_entities = staticmethod(list_billing_entities)
    update = staticmethod(update)
    search = staticmethod(search)
    ensure_billing_entity = staticmethod(ensure_billing_entity)


billing_entity_repo = BillingEntityRepo()
