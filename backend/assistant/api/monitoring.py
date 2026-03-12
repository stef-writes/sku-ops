"""Agent monitoring API — internal endpoints for observability."""

from fastapi import APIRouter, Query

from assistant.application.queries import (
    get_cost_breakdown,
    get_session_trace,
    get_stats,
    list_runs,
)
from shared.api.deps import AdminDep

router = APIRouter(prefix="/admin/agents", tags=["agent-monitoring"])


@router.get("/runs")
async def agent_runs(
    current_user: AdminDep,
    agent: str | None = Query(None),
    session_id: str | None = Query(None),
    minutes: int = Query(60, ge=1, le=10080),
    limit: int = Query(50, ge=1, le=200),
):
    """Recent agent runs with full details."""
    return await list_runs(
        agent_name=agent,
        session_id=session_id,
        minutes=minutes,
        limit=limit,
    )


@router.get("/stats")
async def agent_stats(
    _current_user: AdminDep,
    hours: int = Query(24, ge=1, le=720),
):
    """Aggregate stats: runs per agent, total tokens, total cost, avg duration, error rate."""
    return await get_stats(hours=hours)


@router.get("/sessions/{session_id}")
async def session_trace(
    session_id: str,
    _current_user: AdminDep,
):
    """Full trace of a session: every agent run, tool calls, tokens, in order."""
    return await get_session_trace(session_id)


@router.get("/costs")
async def cost_breakdown(
    _current_user: AdminDep,
    days: int = Query(7, ge=1, le=90),
    group_by: str = Query("agent", pattern="^(agent|model|org)$"),
):
    """Cost breakdown by agent, model, or org."""
    return await get_cost_breakdown(days=days, group_by=group_by)
