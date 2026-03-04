"""Agent monitoring API — internal endpoints for observability."""
from fastapi import APIRouter, Depends, Query

from identity.application.auth_service import get_current_user
from assistant.infrastructure.agent_run_repo import (
    list_runs,
    get_stats,
    get_session_trace,
    get_cost_breakdown,
)

router = APIRouter(prefix="/admin/agents", tags=["agent-monitoring"])


@router.get("/runs")
async def agent_runs(
    agent: str | None = Query(None),
    session_id: str | None = Query(None),
    minutes: int = Query(60, ge=1, le=10080),
    limit: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
):
    """Recent agent runs with full details."""
    return await list_runs(
        agent_name=agent, session_id=session_id,
        org_id=current_user.get("organization_id"),
        minutes=minutes, limit=limit,
    )


@router.get("/stats")
async def agent_stats(
    hours: int = Query(24, ge=1, le=720),
    current_user: dict = Depends(get_current_user),
):
    """Aggregate stats: runs per agent, total tokens, total cost, avg duration, error rate."""
    return await get_stats(hours=hours)


@router.get("/sessions/{session_id}")
async def session_trace(
    session_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Full trace of a session: every agent run, tool calls, tokens, in order."""
    return await get_session_trace(session_id)


@router.get("/costs")
async def cost_breakdown(
    days: int = Query(7, ge=1, le=90),
    group_by: str = Query("agent", pattern="^(agent|model|org)$"),
    current_user: dict = Depends(get_current_user),
):
    """Cost breakdown by agent, model, or org."""
    return await get_cost_breakdown(days=days, group_by=group_by)
