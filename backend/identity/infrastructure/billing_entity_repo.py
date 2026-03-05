"""Billing entity repository — persistence for billing entity master data."""
from datetime import datetime, timezone
from typing import Optional, Union

from identity.domain.billing_entity import BillingEntity
from shared.infrastructure.database import get_connection


def _row_to_dict(row) -> Optional[dict]:
    if row is None:
        return None
    d = dict(row) if hasattr(row, "keys") else {}
    if "is_active" in d:
        d["is_active"] = bool(d["is_active"])
    return d


_COLUMNS = "id, name, contact_name, contact_email, billing_address, payment_terms, xero_contact_id, is_active, organization_id, created_at, updated_at"


async def insert(entity: Union[BillingEntity, dict], conn=None) -> None:
    d = entity if isinstance(entity, dict) else entity.model_dump()
    in_tx = conn is not None
    conn = conn or get_connection()
    await conn.execute(
        f"""INSERT INTO billing_entities ({_COLUMNS})
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            d["id"], d["name"], d.get("contact_name", ""),
            d.get("contact_email", ""), d.get("billing_address", ""),
            d.get("payment_terms", "net_30"), d.get("xero_contact_id"),
            1 if d.get("is_active", True) else 0,
            d["organization_id"], d["created_at"], d["updated_at"],
        ),
    )
    if not in_tx:
        await conn.commit()


async def get_by_id(entity_id: str, organization_id: str) -> Optional[dict]:
    conn = get_connection()
    cursor = await conn.execute(
        f"SELECT {_COLUMNS} FROM billing_entities WHERE id = ? AND organization_id = ?",
        (entity_id, organization_id),
    )
    return _row_to_dict(await cursor.fetchone())


async def get_by_name(name: str, organization_id: str) -> Optional[dict]:
    conn = get_connection()
    cursor = await conn.execute(
        f"SELECT {_COLUMNS} FROM billing_entities WHERE LOWER(TRIM(name)) = ? AND organization_id = ?",
        (name.strip().lower(), organization_id),
    )
    return _row_to_dict(await cursor.fetchone())


async def list_billing_entities(
    organization_id: str,
    is_active: Optional[bool] = None,
    q: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
) -> list:
    conn = get_connection()
    sql = f"SELECT {_COLUMNS} FROM billing_entities WHERE organization_id = ?"
    params: list = [organization_id]
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
    return [_row_to_dict(r) for r in await cursor.fetchall()]


async def update(entity_id: str, updates: dict, organization_id: str) -> Optional[dict]:
    conn = get_connection()
    set_clauses = []
    params = []
    for key in ("name", "contact_name", "contact_email", "billing_address", "payment_terms", "xero_contact_id"):
        if key in updates and updates[key] is not None:
            set_clauses.append(f"{key} = ?")
            params.append(updates[key])
    if "is_active" in updates and updates["is_active"] is not None:
        set_clauses.append("is_active = ?")
        params.append(1 if updates["is_active"] else 0)
    if not set_clauses:
        return await get_by_id(entity_id, organization_id)
    set_clauses.append("updated_at = ?")
    params.append(datetime.now(timezone.utc).isoformat())
    params.extend([entity_id, organization_id])
    await conn.execute(
        f"UPDATE billing_entities SET {', '.join(set_clauses)} WHERE id = ? AND organization_id = ?",
        params,
    )
    await conn.commit()
    return await get_by_id(entity_id, organization_id)


async def search(query: str, organization_id: str, limit: int = 20) -> list:
    """Fast prefix/substring search for autocomplete."""
    conn = get_connection()
    like = f"%{query.lower()}%"
    cursor = await conn.execute(
        f"""SELECT {_COLUMNS} FROM billing_entities
            WHERE organization_id = ? AND is_active = 1
              AND (LOWER(name) LIKE ? OR LOWER(contact_name) LIKE ?)
            ORDER BY name LIMIT ?""",
        (organization_id, like, like, limit),
    )
    return [_row_to_dict(r) for r in await cursor.fetchall()]


async def ensure_billing_entity(name: str, organization_id: str, conn=None) -> dict:
    """Get existing entity by name, or auto-create a minimal one."""
    if not name or not name.strip():
        return {}
    existing = await get_by_name(name, organization_id)
    if existing:
        return existing
    entity = BillingEntity(name=name.strip(), organization_id=organization_id)
    await insert(entity, conn=conn)
    return entity.model_dump()


class BillingEntityRepo:
    insert = staticmethod(insert)
    get_by_id = staticmethod(get_by_id)
    get_by_name = staticmethod(get_by_name)
    list_billing_entities = staticmethod(list_billing_entities)
    update = staticmethod(update)
    search = staticmethod(search)
    ensure_billing_entity = staticmethod(ensure_billing_entity)


billing_entity_repo = BillingEntityRepo()
