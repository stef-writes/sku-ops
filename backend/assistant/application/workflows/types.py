"""Workflow state and result types for DAG execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class FetchSpec:
    """One tool invocation for parallel fetch. result_key maps to the aggregated dict."""

    tool_name: str
    args: dict[str, Any]
    result_key: str


class WorkflowRunner(Protocol[T]):
    """Protocol for runnable workflows."""

    async def __call__(self, deps: WorkflowDeps) -> T: ...


@dataclass
class WorkflowDeps:
    """Dependencies passed into workflow execution. Org/user come from ambient context."""

    org_id: str
    user_id: str
    days: int = 30
    trace_id: str | None = None


@dataclass
class WeeklySalesReportResult:
    """Result of the weekly sales report workflow."""

    revenue_summary: dict[str, Any]
    pl_summary: dict[str, Any]
    top_products: list[dict[str, Any]]
    outstanding_balances: list[dict[str, Any]]
    synthesized_markdown: str


@dataclass
class InventoryOverviewResult:
    """Result of the inventory overview workflow."""

    inventory_stats: dict[str, Any]
    department_health: list[dict[str, Any]]
    low_stock: list[dict[str, Any]]
    slow_movers: list[dict[str, Any]]
    synthesized_markdown: str
