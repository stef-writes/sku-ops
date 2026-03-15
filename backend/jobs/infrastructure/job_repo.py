"""Job repository — persistence for job master data."""

from datetime import UTC, datetime

from jobs.domain.job import Job
from shared.infrastructure.database import get_connection, get_org_id


def _row_to_model(row) -> Job | None:
    if row is None:
        return None
    d = dict(row)
    return Job.model_validate(d)


_COLUMNS = "id, code, name, billing_entity_id, status, service_address, notes, organization_id, created_at, updated_at"


async def insert(job: Job) -> None:
    d = job.model_dump()
    conn = get_connection()
    ins_q = "INSERT INTO jobs ("
    ins_q += _COLUMNS
    ins_q += ") VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)"
    await conn.execute(
        ins_q,
        (
            d["id"],
            d["code"],
            d.get("name", ""),
            d.get("billing_entity_id"),
            d.get("status", "active"),
            d.get("service_address", ""),
            d.get("notes"),
            d["organization_id"],
            d["created_at"],
            d["updated_at"],
        ),
    )
    await conn.commit()


async def get_by_id(job_id: str) -> Job | None:
    conn = get_connection()
    org_id = get_org_id()
    sel_q = "SELECT "
    sel_q += _COLUMNS
    sel_q += " FROM jobs WHERE id = $1 AND organization_id = $2"
    cursor = await conn.execute(sel_q, (job_id, org_id))
    return _row_to_model(await cursor.fetchone())


async def get_by_code(code: str) -> Job | None:
    conn = get_connection()
    org_id = get_org_id()
    sel_q = "SELECT "
    sel_q += _COLUMNS
    sel_q += " FROM jobs WHERE code = $1 AND organization_id = $2"
    cursor = await conn.execute(sel_q, (code, org_id))
    return _row_to_model(await cursor.fetchone())


async def list_jobs(
    status: str | None = None,
    q: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[Job]:
    conn = get_connection()
    org_id = get_org_id()
    sql = "SELECT "
    sql += _COLUMNS
    sql += " FROM jobs WHERE organization_id = $1"
    params: list = [org_id]
    n = 2
    if status:
        sql += f" AND status = ${n}"
        params.append(status)
        n += 1
    if q:
        sql += f" AND (LOWER(code) LIKE ${n} OR LOWER(name) LIKE ${n + 1})"
        like = f"%{q.lower()}%"
        params.extend([like, like])
        n += 2
    sql += f" ORDER BY created_at DESC LIMIT ${n} OFFSET ${n + 1}"
    params.extend([limit, offset])
    cursor = await conn.execute(sql, params)
    return [_row_to_model(r) for r in await cursor.fetchall()]


async def update(job_id: str, updates: dict) -> Job | None:
    conn = get_connection()
    org_id = get_org_id()
    set_clauses = []
    params = []
    n = 1
    for key in ("name", "status", "billing_entity_id", "service_address", "notes"):
        if key in updates and updates[key] is not None:
            set_clauses.append(f"{key} = ${n}")
            params.append(updates[key])
            n += 1
    if not set_clauses:
        return await get_by_id(job_id)
    set_clauses.append(f"updated_at = ${n}")
    params.append(datetime.now(UTC).isoformat())
    n += 1
    params.extend([job_id, org_id])
    await conn.execute(
        "UPDATE jobs SET "
        + ", ".join(set_clauses)
        + f" WHERE id = ${n} AND organization_id = ${n + 1}",
        params,
    )
    await conn.commit()
    return await get_by_id(job_id)


async def search(query: str, limit: int = 20) -> list[Job]:
    """Fast prefix/substring search for autocomplete."""
    conn = get_connection()
    org_id = get_org_id()
    like = f"%{query.lower()}%"
    cursor = await conn.execute(
        "SELECT " + _COLUMNS + " FROM jobs"
        " WHERE organization_id = $1 AND status = 'active'"
        " AND (LOWER(code) LIKE $2 OR LOWER(name) LIKE $3)"
        " ORDER BY code LIMIT $4",
        (org_id, like, like, limit),
    )
    return [_row_to_model(r) for r in await cursor.fetchall()]


async def ensure_job(code: str) -> Job:
    """Get existing job by code, or auto-create a minimal one. Used by write paths."""
    existing = await get_by_code(code)
    if existing:
        return existing
    org_id = get_org_id()
    job = Job(code=code, name=code, organization_id=org_id)
    await insert(job)
    return job


class JobRepo:
    insert = staticmethod(insert)
    get_by_id = staticmethod(get_by_id)
    get_by_code = staticmethod(get_by_code)
    list_jobs = staticmethod(list_jobs)
    update = staticmethod(update)
    search = staticmethod(search)
    ensure_job = staticmethod(ensure_job)


job_repo = JobRepo()
