"""Weekly sales report workflow — parallel tool fetch + LLM synthesis.

Uses base primitives to run 4 finance tools in parallel, then
synthesize into a markdown report.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from assistant.application.workflows.base import run_parallel_fetch, run_synthesis
from assistant.application.workflows.types import FetchSpec, WeeklySalesReportResult

logger = logging.getLogger(__name__)

_SYNTHESIS_PROMPT = (Path(__file__).resolve().parent.parent / "dag_synthesis_prompt.md").read_text(
    encoding="utf-8"
)


def _specs(days: int) -> list[FetchSpec]:
    """Build fetch specs for the weekly sales workflow."""
    return [
        FetchSpec("get_revenue_summary", {"days": days}, "revenue_summary"),
        FetchSpec("get_pl_summary", {"days": days}, "pl_summary"),
        FetchSpec("get_top_products_fin", {"days": days, "limit": 10}, "top_products_raw"),
        FetchSpec("get_outstanding_balances", {"limit": 20}, "outstanding_balances_raw"),
    ]


def _build_synthesis_prompt(data: dict) -> str:
    """Build a prompt for the synthesis LLM from raw tool data."""
    parts = []
    rev = data.get("revenue_summary", {})
    if rev:
        parts.append("## Revenue Summary\n" + json.dumps(rev, indent=2))
    pl = data.get("pl_summary", {})
    if pl:
        parts.append("## P&L Summary\n" + json.dumps(pl, indent=2))
    top_raw = data.get("top_products_raw", {})
    top = top_raw.get("products", []) if isinstance(top_raw, dict) else []
    if top:
        parts.append("## Top Products\n" + json.dumps(top[:10], indent=2))
    bal_raw = data.get("outstanding_balances_raw", {})
    bal = bal_raw.get("balances", []) if isinstance(bal_raw, dict) else []
    if bal:
        parts.append("## Outstanding Balances\n" + json.dumps(bal[:15], indent=2))
    return "\n\n".join(parts) if parts else "No data available."


def _fallback_markdown(data: dict) -> str:
    """Fallback when LLM synthesis fails — basic formatting."""
    lines = ["## Weekly Sales Report"]
    pl = data.get("pl_summary", {})
    if pl:
        lines.append(f"- **Revenue**: ${pl.get('revenue', 0):,.2f}")
        lines.append(f"- **COGS**: ${pl.get('cost_of_goods', 0):,.2f}")
        lines.append(f"- **Gross profit**: ${pl.get('gross_profit', 0):,.2f}")
        lines.append(f"- **Margin**: {pl.get('gross_margin_pct', 0)}%")
    bal_raw = data.get("outstanding_balances_raw", {})
    bal = bal_raw.get("balances", []) if isinstance(bal_raw, dict) else []
    if bal:
        total = sum(b.get("balance", 0) for b in bal)
        lines.append(f"\n**Total outstanding**: ${total:,.2f}")
    return "\n".join(lines)


async def run_weekly_sales_report(days: int = 30) -> WeeklySalesReportResult:
    """Run the weekly sales workflow and return a typed result."""
    data = await run_parallel_fetch(_specs(days))
    markdown = await run_synthesis(
        data,
        _SYNTHESIS_PROMPT,
        _build_synthesis_prompt,
        _fallback_markdown,
    )

    top_raw = data.get("top_products_raw", {})
    top_products = top_raw.get("products", []) if isinstance(top_raw, dict) else []
    bal_raw = data.get("outstanding_balances_raw", {})
    outstanding_balances = bal_raw.get("balances", []) if isinstance(bal_raw, dict) else []

    return WeeklySalesReportResult(
        revenue_summary=data.get("revenue_summary", {}),
        pl_summary=data.get("pl_summary", {}),
        top_products=top_products,
        outstanding_balances=outstanding_balances,
        synthesized_markdown=markdown,
    )
