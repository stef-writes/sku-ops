"""DAG execution plan templates for structured report queries.

Each template defines a set of tool calls and dependencies that can run
concurrently via the DAG executor.
"""

import re
from collections.abc import Callable

from assistant.agents.routing.dag_types import DAGNode, ExecutionPlan


def _inventory_overview() -> ExecutionPlan:
    return ExecutionPlan(
        template_name="inventory_overview",
        nodes={
            "stats": DAGNode("stats", "tool_call", tool="get_inventory_stats", token_budget=300),
            "health": DAGNode(
                "health", "tool_call", tool="get_department_health", token_budget=400
            ),
            "reorder": DAGNode(
                "reorder",
                "tool_call",
                tool="get_reorder_suggestions",
                args={"limit": 10},
                token_budget=500,
            ),
            "slow": DAGNode(
                "slow", "tool_call", tool="get_slow_movers", args={"limit": 10}, token_budget=400
            ),
            "synth": DAGNode(
                "synth",
                "synthesize",
                depends_on=["stats", "health", "reorder", "slow"],
                token_budget=800,
            ),
        },
    )


def _weekly_report() -> ExecutionPlan:
    return ExecutionPlan(
        template_name="weekly_report",
        nodes={
            "revenue": DAGNode(
                "revenue",
                "tool_call",
                tool="get_revenue_summary",
                args={"days": 7},
                token_budget=300,
            ),
            "pl": DAGNode(
                "pl", "tool_call", tool="get_pl_summary", args={"days": 7}, token_budget=300
            ),
            "top": DAGNode(
                "top",
                "tool_call",
                tool="get_top_products",
                args={"days": 7, "limit": 10},
                token_budget=500,
            ),
            "balances": DAGNode(
                "balances", "tool_call", tool="get_outstanding_balances", token_budget=500
            ),
            "synth": DAGNode(
                "synth",
                "synthesize",
                depends_on=["revenue", "pl", "top", "balances"],
                token_budget=800,
            ),
        },
    )


def _dashboard_overview() -> ExecutionPlan:
    return ExecutionPlan(
        template_name="dashboard_overview",
        nodes={
            "stats": DAGNode("stats", "tool_call", tool="get_inventory_stats", token_budget=300),
            "revenue": DAGNode(
                "revenue",
                "tool_call",
                tool="get_revenue_summary",
                args={"days": 7},
                token_budget=300,
            ),
            "balances": DAGNode(
                "balances",
                "tool_call",
                tool="get_outstanding_balances",
                args={"limit": 5},
                token_budget=400,
            ),
            "stockout": DAGNode(
                "stockout",
                "tool_call",
                tool="forecast_stockout",
                args={"limit": 5},
                token_budget=400,
            ),
            "synth": DAGNode(
                "synth",
                "synthesize",
                depends_on=["stats", "revenue", "balances", "stockout"],
                token_budget=800,
            ),
        },
    )


def _stockout_report() -> ExecutionPlan:
    return ExecutionPlan(
        template_name="stockout_report",
        nodes={
            "forecast": DAGNode(
                "forecast",
                "tool_call",
                tool="forecast_stockout",
                args={"limit": 15},
                token_budget=600,
            ),
            "reorder": DAGNode(
                "reorder",
                "tool_call",
                tool="get_reorder_suggestions",
                args={"limit": 15},
                token_budget=500,
            ),
            "synth": DAGNode(
                "synth", "synthesize", depends_on=["forecast", "reorder"], token_budget=600
            ),
        },
    )


def _attention_report() -> ExecutionPlan:
    """What needs my attention today — low stock + pending requests + balances + stockout."""
    return ExecutionPlan(
        template_name="attention_report",
        nodes={
            "low_stock": DAGNode(
                "low_stock",
                "tool_call",
                tool="list_low_stock",
                args={"limit": 10},
                token_budget=400,
            ),
            "pending": DAGNode(
                "pending",
                "tool_call",
                tool="list_pending_material_requests",
                args={"limit": 10},
                token_budget=400,
            ),
            "balances": DAGNode(
                "balances",
                "tool_call",
                tool="get_outstanding_balances",
                args={"limit": 10},
                token_budget=400,
            ),
            "forecast": DAGNode(
                "forecast",
                "tool_call",
                tool="forecast_stockout",
                args={"limit": 10},
                token_budget=400,
            ),
            "synth": DAGNode(
                "synth",
                "synthesize",
                depends_on=["low_stock", "pending", "balances", "forecast"],
                token_budget=800,
            ),
        },
    )


def _financial_report() -> ExecutionPlan:
    """Finance overview — revenue + P&L + balances + top products."""
    return ExecutionPlan(
        template_name="financial_report",
        nodes={
            "revenue": DAGNode(
                "revenue",
                "tool_call",
                tool="get_revenue_summary",
                args={"days": 30},
                token_budget=300,
            ),
            "pl": DAGNode(
                "pl", "tool_call", tool="get_pl_summary", args={"days": 30}, token_budget=300
            ),
            "balances": DAGNode(
                "balances",
                "tool_call",
                tool="get_outstanding_balances",
                args={"limit": 10},
                token_budget=500,
            ),
            "top": DAGNode(
                "top",
                "tool_call",
                tool="get_top_products",
                args={"days": 30, "limit": 10},
                token_budget=500,
            ),
            "synth": DAGNode(
                "synth",
                "synthesize",
                depends_on=["revenue", "pl", "balances", "top"],
                token_budget=800,
            ),
        },
    )


def _reorder_report() -> ExecutionPlan:
    """Reorder priority — suggestions + slow movers + stockout forecast."""
    return ExecutionPlan(
        template_name="reorder_report",
        nodes={
            "reorder": DAGNode(
                "reorder",
                "tool_call",
                tool="get_reorder_suggestions",
                args={"limit": 15},
                token_budget=500,
            ),
            "slow": DAGNode(
                "slow", "tool_call", tool="get_slow_movers", args={"limit": 10}, token_budget=400
            ),
            "forecast": DAGNode(
                "forecast",
                "tool_call",
                tool="forecast_stockout",
                args={"limit": 10},
                token_budget=500,
            ),
            "synth": DAGNode(
                "synth", "synthesize", depends_on=["reorder", "slow", "forecast"], token_budget=700
            ),
        },
    )


def _low_stock_report() -> ExecutionPlan:
    """Low stock deep dive — low stock list + reorder suggestions."""
    return ExecutionPlan(
        template_name="low_stock_report",
        nodes={
            "low": DAGNode(
                "low", "tool_call", tool="list_low_stock", args={"limit": 20}, token_budget=500
            ),
            "reorder": DAGNode(
                "reorder",
                "tool_call",
                tool="get_reorder_suggestions",
                args={"limit": 20},
                token_budget=500,
            ),
            "synth": DAGNode(
                "synth", "synthesize", depends_on=["low", "reorder"], token_budget=600
            ),
        },
    )


def _search_then_detail() -> ExecutionPlan:
    return ExecutionPlan(
        template_name="search_then_detail",
        nodes={
            "search": DAGNode("search", "tool_call", tool="search_products", token_budget=500),
            "detail": DAGNode(
                "detail",
                "conditional",
                tool="get_product_details",
                depends_on=["search"],
                condition="search.count == 1",
                token_budget=400,
            ),
            "synth": DAGNode(
                "synth", "synthesize", depends_on=["search", "detail"], token_budget=600
            ),
        },
    )


TEMPLATE_PATTERNS: list[tuple[re.Pattern, Callable[[], ExecutionPlan]]] = [
    (
        re.compile(
            r"(full|complete|deep)\s+(inventory|stock)\s+(analysis|report|overview|health)",
            re.IGNORECASE,
        ),
        _inventory_overview,
    ),
    (
        re.compile(r"inventory\s+(overview|analysis|health|report)", re.IGNORECASE),
        _inventory_overview,
    ),
    (re.compile(r"(stock|inventory)\s+health", re.IGNORECASE), _inventory_overview),
    (
        re.compile(r"(weekly|week|7.day|periodic)\s+(sales|report|summary)", re.IGNORECASE),
        _weekly_report,
    ),
    (
        re.compile(r"(write|give|create)\s+.{0,20}(weekly|week)\s+(report|summary)", re.IGNORECASE),
        _weekly_report,
    ),
    (
        re.compile(r"(dashboard|business|store|shop)\s+(overview|summary|status)", re.IGNORECASE),
        _dashboard_overview,
    ),
    (re.compile(r"how.s the (business|store|shop) doing", re.IGNORECASE), _dashboard_overview),
    (
        re.compile(r"(full|complete)\s+(store|business)\s+overview", re.IGNORECASE),
        _dashboard_overview,
    ),
    (re.compile(r"give me .{0,20}(overview|summary)", re.IGNORECASE), _dashboard_overview),
    (
        re.compile(
            r"(stockout|running out|going to run out).*(forecast|report|risk|prediction)",
            re.IGNORECASE,
        ),
        _stockout_report,
    ),
    (re.compile(r"(what|which).*(running out|run out|stockout)", re.IGNORECASE), _stockout_report),
    (re.compile(r"at risk of (stocking out|running out)", re.IGNORECASE), _stockout_report),
    (
        re.compile(r"what needs?.{0,15}(attention|focus|my attention)", re.IGNORECASE),
        _attention_report,
    ),
    (re.compile(r"what should I (focus|look at|prioriti[sz]e)", re.IGNORECASE), _attention_report),
    (
        re.compile(r"(critical|urgent).*(stock|request|invoice|alert)", re.IGNORECASE),
        _attention_report,
    ),
    (re.compile(r"financ\w*\s+(overview|summary|report|health)", re.IGNORECASE), _financial_report),
    (
        re.compile(r"(P&?L|profit.{0,5}loss)\s+(summary|report|overview)", re.IGNORECASE),
        _financial_report,
    ),
    (re.compile(r"how.{0,10}(money|financ|revenue)", re.IGNORECASE), _financial_report),
    (re.compile(r"(what should we|what do we need to)\s+reorder", re.IGNORECASE), _reorder_report),
    (re.compile(r"reorder\s+(priority|list|suggestions?|report)", re.IGNORECASE), _reorder_report),
    (
        re.compile(r"(what|which).*(need|should).*(restock|reorder|buy|order)", re.IGNORECASE),
        _reorder_report,
    ),
    (
        re.compile(r"(low stock|below reorder).*(report|analysis|detail|alert)", re.IGNORECASE),
        _low_stock_report,
    ),
    (
        re.compile(r"(all|every|list).*(low stock|running low|below)", re.IGNORECASE),
        _low_stock_report,
    ),
]


def match_report(user_message: str) -> ExecutionPlan | None:
    """Return an ExecutionPlan if the query matches a known template, else None."""
    for pattern, builder in TEMPLATE_PATTERNS:
        if pattern.search(user_message):
            return builder()
    return None
