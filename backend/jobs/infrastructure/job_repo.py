"""Job repository — persistence for job master data."""
from datetime import UTC
from typing import Optional, Union

from jobs.domain.job import Job
from shared.infrastructure.database import get_connection


def _row_to_dict(row) -> dict | None:
    if row is None:
        return None
    return dict(row) if hasattr(row, "keys") else {}


_COLUMNS = "id, code, name, billing_entity_id, status, service_address, notes, organization_id, created_at, updated_at"


async def insert(job: Job | dict, conn=None) -> None:
    d = job if isinstance(job, dict) else job.model_dump()
    in_tx = conn is not None
    conn = conn or get_connection()
    await conn.execute(
        f"""INSERT INTO jobs ({_COLUMNS})
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            d["id"], d["code"], d.get("name", ""), d.get("billing_entity_id"),
            d.get("status", "active"), d.get("service_address", ""),
            d.get("notes"), d["organization_id"],
            d["created_at"], d["updated_at"],
        ),
    )
    if not in_tx:
        await conn.commit()


async def get_by_id(job_id: str, organization_id: str) -> dict | None:
    conn = get_connection()
    cursor = await conn.execute(
        f"SELECT {_COLUMNS} FROM jobs WHERE id = ? AND organization_id = ?",
        (job_id, organization_id),
    )
    return _row_to_dict(await cursor.fetchone())


async def get_by_code(code: str, organization_id: str) -> dict | None:
    conn = get_connection()
    cursor = await conn.execute(
        f"SELECT {_COLUMNS} FROM jobs WHERE code = ? AND organization_id = ?",
        (code, organization_id),
    )
    return _row_to_dict(await cursor.fetchone())


async def list_jobs(
    organization_id: str,
    status: str | None = None,
    q: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list:
    conn = get_connection()
    sql = f"SELECT {_COLUMNS} FROM jobs WHERE organization_id = ?"
    params: list = [organization_id]
    if status:
        sql += " AND status = ?"
        params.append(status)
    if q:
        sql += " AND (LOWER(code) LIKE ? OR LOWER(name) LIKE ?)"
        like = f"%{q.lower()}%"
        params.extend([like, like])
    sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    cursor = await conn.execute(sql, params)
    return [_row_to_dict(r) for r in await cursor.fetchall()]


async def update(job_id: str, updates: dict, organization_id: str) -> dict | None:
    conn = get_connection()
    set_clauses = []
    params = []
    for key in ("name", "status", "billing_entity_id", "service_address", "notes"):
        if key in updates and updates[key] is not None:
            set_clauses.append(f"{key} = ?")
            params.append(updates[key])
    if not set_clauses:
        return await get_by_id(job_id, organization_id)
    from datetime import datetime, timezone
    set_clauses.append("updated_at = ?")
    params.append(datetime.now(UTC).isoformat())
    params.extend([job_id, organization_id])
    await conn.execute(
        f"UPDATE jobs SET {', '.join(set_clauses)} WHERE id = ? AND organization_id = ?",
        params,
    )
    await conn.commit()
    return await get_by_id(job_id, organization_id)


async def search(query: str, organization_id: str, limit: int = 20) -> list:
    """Fast prefix/substring search for autocomplete."""
    conn = get_connection()
    like = f"%{query.lower()}%"
    cursor = await conn.execute(
        f"""SELECT {_COLUMNS} FROM jobs
            WHERE organization_id = ? AND status = 'active'
              AND (LOWER(code) LIKE ? OR LOWER(name) LIKE ?)
            ORDER BY code LIMIT ?""",
        (organization_id, like, like, limit),
    )
    return [_row_to_dict(r) for r in await cursor.fetchall()]


async def ensure_job(code: str, organization_id: str, conn=None) -> dict:
    """Get existing job by code, or auto-create a minimal one. Used by write paths."""
    existing = await get_by_code(code, organization_id)
    if existing:
        return existing
    job = Job(code=code, name=code, organization_id=organization_id)
    await insert(job, conn=conn)
    return job.model_dump()


class JobRepo:
    insert = staticmethod(insert)
    get_by_id = staticmethod(get_by_id)
    get_by_code = staticmethod(get_by_code)
    list_jobs = staticmethod(list_jobs)
    update = staticmethod(update)
    search = staticmethod(search)
    ensure_job = staticmethod(ensure_job)


job_repo = JobRepo()
