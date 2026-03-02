"""
RouterAgent: classifies user intent → dispatches to the right specialist agent.
Uses a single fast Haiku call (no ReAct loop) to classify, then runs the specialist.
"""
import asyncio
import json
import logging

from config import ANTHROPIC_AVAILABLE, ANTHROPIC_API_KEY, ANTHROPIC_FAST_MODEL

logger = logging.getLogger(__name__)

_AGENTS = ("inventory", "ops", "finance", "insights")

_ROUTER_SYSTEM = """You classify hardware store assistant questions into exactly one domain.

Domains:
- inventory: products, stock levels, SKUs, barcodes, departments, vendors, reorder points, UOM, product details, search
- ops: contractors, withdrawals, material requests, jobs, job materials, recent activity, field operations
- finance: invoices, payments, outstanding balances, accounts receivable, revenue, P&L, financial reports
- insights: trends, top-selling products, usage velocity, stockout forecasting, analytics, performance

Rules:
- Return ONLY valid JSON: {"agent": "<domain>"}
- Default to "inventory" for general or ambiguous questions
- Pick the MOST specific domain — don't default to inventory if finance/ops/insights clearly fits"""

_FALLBACK = "inventory"


def _get_client():
    if not ANTHROPIC_AVAILABLE:
        return None
    try:
        import anthropic
        return anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    except ImportError:
        return None


async def classify(user_message: str) -> str:
    """Classify user message → agent name. Returns fallback on any error."""
    client = _get_client()
    if not client:
        return _FALLBACK
    try:
        response = await asyncio.to_thread(
            client.messages.create,
            model=ANTHROPIC_FAST_MODEL,
            system=_ROUTER_SYSTEM,
            messages=[{"role": "user", "content": user_message}],
            max_tokens=64,
        )
        text = response.content[0].text.strip()
        data = json.loads(text)
        agent = data.get("agent", _FALLBACK).lower()
        return agent if agent in _AGENTS else _FALLBACK
    except Exception as e:
        logger.debug(f"Router classify error (using fallback): {e}")
        return _FALLBACK


def _get_agent_module(agent_name: str):
    if agent_name == "inventory":
        from services.agents import inventory
        return inventory
    if agent_name == "ops":
        from services.agents import ops
        return ops
    if agent_name == "finance":
        from services.agents import finance
        return finance
    if agent_name == "insights":
        from services.agents import insights
        return insights
    from services.agents import inventory
    return inventory


async def chat(
    messages: list[dict],
    user_message: str,
    history: list[dict] | None,
    ctx: dict,
) -> dict:
    """
    Route user message to the appropriate specialist agent.
    Returns the specialist's response with an added 'agent' field.
    """
    if not ANTHROPIC_AVAILABLE:
        return {
            "response": (
                "Chat assistant requires an Anthropic API key. "
                "Add ANTHROPIC_API_KEY to backend/.env."
            ),
            "tool_calls": [],
            "history": [],
            "agent": None,
        }

    agent_name = await classify(user_message)
    logger.info(f"Router → {agent_name} (message: {user_message[:60]!r})")

    agent_module = _get_agent_module(agent_name)
    return await agent_module.chat(messages, user_message, history, ctx)
