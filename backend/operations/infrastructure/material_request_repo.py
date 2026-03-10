"""Material request repository."""

import json

from kernel.errors import InvalidTransitionError
from operations.domain.material_request import MaterialRequest
from shared.infrastructure.config import DEFAULT_ORG_ID
from shared.infrastructure.database import get_connection


def _row_to_dict(row) -> dict | None:
    if row is None:
        return None
    d = dict(row) if hasattr(row, "keys") else {}
    if d and "items" in d and isinstance(d["items"], str):
        d["items"] = json.loads(d["items"]) if d["items"] else []
    return d


async def insert(request: MaterialRequest | dict, conn=None) -> None:
    request_dict = request if isinstance(request, dict) else request.model_dump()
    in_transaction = conn is not None
    conn = conn or get_connection()
    org_id = request_dict.get("organization_id") or DEFAULT_ORG_ID
    items_json = json.dumps(
        [i if isinstance(i, dict) else i.model_dump() for i in request_dict["items"]]
    )
    await conn.execute(
        """INSERT INTO material_requests (id, contractor_id, contractor_name, items, status, withdrawal_id,
           job_id, service_address, notes, created_at, processed_at, processed_by_id, organization_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            request_dict["id"],
            request_dict["contractor_id"],
            request_dict.get("contractor_name", ""),
            items_json,
            request_dict.get("status", "pending"),
            request_dict.get("withdrawal_id"),
            request_dict.get("job_id"),
            request_dict.get("service_address"),
            request_dict.get("notes"),
            request_dict.get("created_at", ""),
            request_dict.get("processed_at"),
            request_dict.get("processed_by_id"),
            org_id,
        ),
    )
    if not in_transaction:
        await conn.commit()


async def get_by_id(request_id: str, organization_id: str | None = None) -> dict | None:
    conn = get_connection()
    org_id = organization_id or DEFAULT_ORG_ID
    cursor = await conn.execute(
        "SELECT * FROM material_requests WHERE id = ? AND (organization_id = ? OR organization_id IS NULL)",
        (request_id, org_id),
    )
    row = await cursor.fetchone()
    return _row_to_dict(row)


async def list_pending(organization_id: str | None = None, limit: int = 100) -> list:
    conn = get_connection()
    org_id = organization_id or DEFAULT_ORG_ID
    cursor = await conn.execute(
        "SELECT * FROM material_requests WHERE status = 'pending' AND (organization_id = ? OR organization_id IS NULL) ORDER BY created_at DESC LIMIT ?",
        (org_id, limit),
    )
    rows = await cursor.fetchall()
    return [_row_to_dict(r) for r in rows]


async def list_by_contractor(
    contractor_id: str, organization_id: str | None = None, limit: int = 100
) -> list:
    conn = get_connection()
    org_id = organization_id or DEFAULT_ORG_ID
    cursor = await conn.execute(
        "SELECT * FROM material_requests WHERE contractor_id = ? AND (organization_id = ? OR organization_id IS NULL) ORDER BY created_at DESC LIMIT ?",
        (contractor_id, org_id, limit),
    )
    rows = await cursor.fetchall()
    return [_row_to_dict(r) for r in rows]


async def mark_processed(
    request_id: str,
    withdrawal_id: str,
    processed_by_id: str,
    processed_at: str,
    conn=None,
) -> bool:
    in_transaction = conn is not None
    conn = conn or get_connection()
    cursor = await conn.execute(
        """UPDATE material_requests SET status = 'processed', withdrawal_id = ?, processed_by_id = ?, processed_at = ?
           WHERE id = ? AND status = 'pending'""",
        (withdrawal_id, processed_by_id, processed_at, request_id),
    )
    if cursor.rowcount == 0:
        raise InvalidTransitionError("MaterialRequest", "processed", "processed")
    if not in_transaction:
        await conn.commit()
    return True


class MaterialRequestRepo:
    insert = staticmethod(insert)
    get_by_id = staticmethod(get_by_id)
    list_pending = staticmethod(list_pending)
    list_by_contractor = staticmethod(list_by_contractor)
    mark_processed = staticmethod(mark_processed)


material_request_repo = MaterialRequestRepo()
