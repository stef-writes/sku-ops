"""Inventory overview workflow — parallel tool fetch + LLM synthesis.

Runs get_inventory_stats, get_department_health, list_low_stock, get_slow_movers
in parallel, then synthesizes into a markdown report.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from assistant.application.workflows.base import run_parallel_fetch, run_synthesis
from assistant.application.workflows.types import FetchSpec, InventoryOverviewResult

logger = logging.getLogger(__name__)

_SYNTHESIS_PROMPT = (Path(__file__).resolve().parent.parent / "dag_synthesis_prompt.md").read_text(
    encoding="utf-8"
)


def _specs(limit: int = 20, days: int = 30) -> list[FetchSpec]:
    """Build fetch specs for the inventory overview workflow."""
    return [
        FetchSpec("get_inventory_stats", {}, "inventory_stats"),
        FetchSpec("get_department_health", {}, "department_health_raw"),
        FetchSpec("list_low_stock", {"limit": limit}, "low_stock_raw"),
        FetchSpec("get_slow_movers", {"limit": limit, "days": days}, "slow_movers_raw"),
    ]


async def run_inventory_overview(
    limit: int = 20,
    days: int = 30,
) -> InventoryOverviewResult:
    """Run the inventory overview workflow and return a typed result."""
    data = await run_parallel_fetch(_specs(limit=limit, days=days))
    department_health = (
        data.get("department_health_raw", {}).get("departments", [])
        if isinstance(data.get("department_health_raw"), dict)
        else []
    )
    low_stock = (
        data.get("low_stock_raw", {}).get("products", [])
        if isinstance(data.get("low_stock_raw"), dict)
        else []
    )
    slow_movers = (
        data.get("slow_movers_raw", {}).get("slow_movers", [])
        if isinstance(data.get("slow_movers_raw"), dict)
        else []
    )
    data_for_synthesis = {
        "inventory_stats": data.get("inventory_stats", {}),
        "department_health": department_health,
        "low_stock": low_stock,
        "slow_movers": slow_movers,
    }
    markdown = await run_synthesis(
        data_for_synthesis,
        _SYNTHESIS_PROMPT,
        _build_synthesis_prompt,
        _fallback_markdown,
    )
    return InventoryOverviewResult(
        inventory_stats=data_for_synthesis["inventory_stats"],
        department_health=department_health,
        low_stock=low_stock,
        slow_movers=slow_movers,
        synthesized_markdown=markdown,
    )


def _build_synthesis_prompt(data: dict) -> str:
    """Build a prompt for the synthesis LLM from raw tool data."""
    parts = []
    stats = data.get("inventory_stats", {})
    if stats:
        parts.append("## Inventory Stats\n" + json.dumps(stats, indent=2))
    depts = data.get("department_health", [])
    if depts:
        parts.append("## Department Health\n" + json.dumps(depts[:15], indent=2))
    low = data.get("low_stock", [])
    if low:
        parts.append("## Low Stock Products\n" + json.dumps(low[:20], indent=2))
    slow = data.get("slow_movers", [])
    if slow:
        parts.append("## Slow Movers\n" + json.dumps(slow[:20], indent=2))
    return "\n\n".join(parts) if parts else "No data available."


def _fallback_markdown(data: dict) -> str:
    """Fallback when LLM synthesis fails."""
    lines = ["## Inventory Overview"]
    stats = data.get("inventory_stats", {})
    if stats:
        lines.append(f"- **Total SKUs**: {stats.get('total_skus', 0)}")
        lines.append(f"- **Low stock count**: {stats.get('low_stock_count', 0)}")
        lines.append(f"- **Out of stock**: {stats.get('out_of_stock_count', 0)}")
    return "\n".join(lines)
