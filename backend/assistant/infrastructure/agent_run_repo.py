"""Repository for agent_runs — insert + query for monitoring."""

import json
import uuid
from datetime import UTC, datetime

from shared.infrastructure.database import get_connection, get_org_id


async def log_agent_run(
    *,
    session_id: str,
    user_id: str = "",
    agent_name: str,
    model: str,
    mode: str = "fast",
    user_message: str = "",
    response_text: str = "",
    tool_calls: list[dict] | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cost_usd: float = 0.0,
    duration_ms: int = 0,
    attempts: int = 1,
    error: str | None = None,
    error_kind: str | None = None,
    parent_run_id: str | None = None,
    handoff_from: str | None = None,
) -> str:
    run_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    conn = get_connection()
    org_id = get_org_id()
    await conn.execute(
        """INSERT INTO agent_runs
           (id, session_id, org_id, user_id, agent_name, model, mode,
            user_message, response_text, tool_calls,
            input_tokens, output_tokens, cost_usd, duration_ms,
            attempts, error, error_kind, parent_run_id, handoff_from, created_at)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20)""",
        (
            run_id,
            session_id,
            org_id,
            user_id,
            agent_name,
            model,
            mode,
            (user_message or "")[:2000],
            (response_text or "")[:4000],
            json.dumps(tool_calls or []),
            input_tokens,
            output_tokens,
            round(cost_usd, 6),
            duration_ms,
            attempts,
            error,
            error_kind,
            parent_run_id,
            handoff_from,
            now,
        ),
    )
    await conn.commit()
    return run_id


async def list_runs(
    *,
    agent_name: str | None = None,
    session_id: str | None = None,
    org_id: str | None = None,
    minutes: int = 60,
    limit: int = 50,
) -> list[dict]:
    conn = get_connection()
    clauses = [f"created_at >= NOW() - INTERVAL '{minutes} minutes'"]
    params: list = []
    n = 1

    if agent_name:
        clauses.append(f"agent_name = ${n}")
        params.append(agent_name)
        n += 1
    if session_id:
        clauses.append(f"session_id = ${n}")
        params.append(session_id)
        n += 1
    if org_id:
        clauses.append(f"org_id = ${n}")
        params.append(org_id)
        n += 1

    where = " AND ".join(clauses)
    params.append(limit)
    query = "SELECT * FROM agent_runs WHERE "
    query += where
    query += f" ORDER BY created_at DESC LIMIT ${n}"
    cur = await conn.execute(query, params)
    return [dict(r) for r in await cur.fetchall()]


async def get_stats(*, hours: int = 24) -> dict:
    conn = get_connection()
    since_expr = f"created_at >= NOW() - INTERVAL '{hours} hours'"

    cur = await conn.execute(
        "SELECT"
        " agent_name,"
        " COUNT(*) as runs,"
        " SUM(input_tokens) as total_input_tokens,"
        " SUM(output_tokens) as total_output_tokens,"
        " SUM(cost_usd) as total_cost,"
        " AVG(duration_ms) as avg_duration_ms,"
        " MAX(duration_ms) as max_duration_ms,"
        " SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) as errors"
        " FROM agent_runs"
        " WHERE " + since_expr + " GROUP BY agent_name"
        " ORDER BY runs DESC",
        [],
    )
    by_agent = await cur.fetchall()

    cur = await conn.execute(
        "SELECT"
        " COUNT(*) as total_runs,"
        " SUM(input_tokens) as total_input_tokens,"
        " SUM(output_tokens) as total_output_tokens,"
        " SUM(cost_usd) as total_cost,"
        " AVG(duration_ms) as avg_duration_ms,"
        " SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) as total_errors"
        " FROM agent_runs"
        " WHERE " + since_expr,
        [],
    )
    totals = await cur.fetchone()

    cur = await conn.execute(
        "SELECT model, COUNT(*) as runs, SUM(cost_usd) as cost"
        " FROM agent_runs WHERE " + since_expr + " GROUP BY model ORDER BY cost DESC",
        [],
    )
    by_model = await cur.fetchall()

    return {
        "period_hours": hours,
        "totals": totals,
        "by_agent": by_agent,
        "by_model": by_model,
    }


async def get_session_trace(session_id: str) -> list[dict]:
    conn = get_connection()
    cur = await conn.execute(
        "SELECT * FROM agent_runs WHERE session_id = $1 ORDER BY created_at ASC",
        (session_id,),
    )
    rows: list[dict] = [dict(r) for r in await cur.fetchall()]
    for r in rows:
        if isinstance(r.get("tool_calls"), str):
            r["tool_calls"] = json.loads(r["tool_calls"])
    return rows


async def get_cost_breakdown(*, days: int = 7, group_by: str = "agent") -> list[dict]:
    conn = get_connection()
    since_expr = f"created_at >= NOW() - INTERVAL '{days} days'"
    day_expr = "(created_at)::date"

    col = {"agent": "agent_name", "model": "model", "org": "org_id"}.get(group_by, "agent_name")
    query = "SELECT "
    query += col
    query += " as group_key, "
    query += day_expr
    query += (
        " as day,"
        " COUNT(*) as runs,"
        " SUM(input_tokens) as input_tokens,"
        " SUM(output_tokens) as output_tokens,"
        " SUM(cost_usd) as cost"
        " FROM agent_runs"
        " WHERE "
    )
    query += since_expr
    query += " GROUP BY "
    query += col
    query += ", "
    query += day_expr
    query += " ORDER BY day DESC, cost DESC"
    cur = await conn.execute(query, [])
    return [dict(r) for r in await cur.fetchall()]
