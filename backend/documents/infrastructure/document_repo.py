"""Document repository — persistence for uploaded/parsed documents."""
import json
from typing import Optional, Union

from documents.domain.document import Document
from shared.infrastructure.database import get_connection


def _row_to_dict(row) -> Optional[dict]:
    if row is None:
        return None
    d = dict(row) if hasattr(row, "keys") else {}
    if d and "parsed_data" in d and isinstance(d["parsed_data"], str):
        try:
            d["parsed_data"] = json.loads(d["parsed_data"])
        except (json.JSONDecodeError, TypeError):
            pass
    return d


_COLUMNS = "id, filename, document_type, vendor_name, file_hash, file_size, mime_type, parsed_data, po_id, status, uploaded_by_id, organization_id, created_at, updated_at"


async def insert(doc: Union[Document, dict], conn=None) -> None:
    d = doc if isinstance(doc, dict) else doc.model_dump()
    in_tx = conn is not None
    conn = conn or get_connection()
    parsed = d.get("parsed_data")
    if parsed and not isinstance(parsed, str):
        parsed = json.dumps(parsed)
    await conn.execute(
        f"""INSERT INTO documents ({_COLUMNS})
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            d["id"], d["filename"], d.get("document_type", "other"),
            d.get("vendor_name"), d.get("file_hash", ""),
            d.get("file_size", 0), d.get("mime_type", ""),
            parsed, d.get("po_id"),
            d.get("status", "parsed"), d["uploaded_by_id"],
            d["organization_id"], d["created_at"], d["updated_at"],
        ),
    )
    if not in_tx:
        await conn.commit()


async def get_by_id(doc_id: str, organization_id: str) -> Optional[dict]:
    conn = get_connection()
    cursor = await conn.execute(
        f"SELECT {_COLUMNS} FROM documents WHERE id = ? AND organization_id = ?",
        (doc_id, organization_id),
    )
    return _row_to_dict(await cursor.fetchone())


async def list_documents(
    organization_id: str,
    status: Optional[str] = None,
    vendor_name: Optional[str] = None,
    po_id: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> list:
    conn = get_connection()
    sql = f"SELECT {_COLUMNS} FROM documents WHERE organization_id = ?"
    params: list = [organization_id]
    if status:
        sql += " AND status = ?"
        params.append(status)
    if vendor_name:
        sql += " AND LOWER(vendor_name) LIKE ?"
        params.append(f"%{vendor_name.lower()}%")
    if po_id:
        sql += " AND po_id = ?"
        params.append(po_id)
    sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    cursor = await conn.execute(sql, params)
    return [_row_to_dict(r) for r in await cursor.fetchall()]


async def update_status(doc_id: str, status: str, po_id: Optional[str] = None, conn=None) -> None:
    from datetime import datetime, timezone
    in_tx = conn is not None
    conn = conn or get_connection()
    if po_id:
        await conn.execute(
            "UPDATE documents SET status = ?, po_id = ?, updated_at = ? WHERE id = ?",
            (status, po_id, datetime.now(timezone.utc).isoformat(), doc_id),
        )
    else:
        await conn.execute(
            "UPDATE documents SET status = ?, updated_at = ? WHERE id = ?",
            (status, datetime.now(timezone.utc).isoformat(), doc_id),
        )
    if not in_tx:
        await conn.commit()


class DocumentRepo:
    insert = staticmethod(insert)
    get_by_id = staticmethod(get_by_id)
    list_documents = staticmethod(list_documents)
    update_status = staticmethod(update_status)


document_repo = DocumentRepo()
