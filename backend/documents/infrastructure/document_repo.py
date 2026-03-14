"""Document repository — persistence for uploaded/parsed documents."""

import contextlib
import json
from datetime import UTC, datetime

from documents.domain.document import Document
from shared.infrastructure.database import get_connection, get_org_id


def _row_to_model(row) -> Document | None:
    if row is None:
        return None
    d = dict(row)
    if "parsed_data" in d and isinstance(d["parsed_data"], str):
        with contextlib.suppress(json.JSONDecodeError, TypeError):
            d["parsed_data"] = json.loads(d["parsed_data"])
    if d.get("parsed_data") and not isinstance(d["parsed_data"], str):
        d["parsed_data"] = json.dumps(d["parsed_data"])
    return Document.model_validate(d)


_COLUMNS = "id, filename, document_type, vendor_name, file_hash, file_size, mime_type, parsed_data, po_id, status, uploaded_by_id, organization_id, created_at, updated_at"


async def insert(doc: Document) -> None:
    d = doc.model_dump()
    conn = get_connection()
    parsed = d.get("parsed_data")
    if parsed and not isinstance(parsed, str):
        parsed = json.dumps(parsed)
    await conn.execute(
        "INSERT INTO documents (" + _COLUMNS + ")"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            d["id"],
            d["filename"],
            d.get("document_type", "other"),
            d.get("vendor_name"),
            d.get("file_hash", ""),
            d.get("file_size", 0),
            d.get("mime_type", ""),
            parsed,
            d.get("po_id"),
            d.get("status", "parsed"),
            d["uploaded_by_id"],
            d["organization_id"],
            d["created_at"],
            d["updated_at"],
        ),
    )
    await conn.commit()


async def get_by_id(doc_id: str) -> Document | None:
    conn = get_connection()
    org_id = get_org_id()
    cursor = await conn.execute(
        "SELECT " + _COLUMNS + " FROM documents WHERE id = ? AND organization_id = ?",
        (doc_id, org_id),
    )
    return _row_to_model(await cursor.fetchone())


async def list_documents(
    status: str | None = None,
    vendor_name: str | None = None,
    po_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Document]:
    conn = get_connection()
    org_id = get_org_id()
    sql = "SELECT " + _COLUMNS + " FROM documents WHERE organization_id = ?"
    params: list = [org_id]
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
    return [_row_to_model(r) for r in await cursor.fetchall()]


async def update_status(doc_id: str, status: str, po_id: str | None = None) -> None:
    conn = get_connection()
    if po_id:
        await conn.execute(
            "UPDATE documents SET status = ?, po_id = ?, updated_at = ? WHERE id = ?",
            (status, po_id, datetime.now(UTC).isoformat(), doc_id),
        )
    else:
        await conn.execute(
            "UPDATE documents SET status = ?, updated_at = ? WHERE id = ?",
            (status, datetime.now(UTC).isoformat(), doc_id),
        )
    await conn.commit()


class DocumentRepo:
    insert = staticmethod(insert)
    get_by_id = staticmethod(get_by_id)
    list_documents = staticmethod(list_documents)
    update_status = staticmethod(update_status)


document_repo = DocumentRepo()
