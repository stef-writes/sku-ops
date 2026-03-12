"""DAG execution engine for structured, parallel tool execution.

Decomposes queries into a directed acyclic graph of tool calls and synthesis
steps.  Independent nodes run concurrently via asyncio.gather.  Each node has
a token budget enforced through budget_tool_result.

Queries that don't match a known template fall through to standard agent
execution (no DAG overhead).

Types and templates are in dag_types.py and dag_templates.py respectively.
"""

import asyncio
import json
import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any

from assistant.agents.core.tokens import budget_tool_result, count_tokens
from assistant.agents.routing.dag_templates import match_report  # noqa: F401
from assistant.agents.routing.dag_types import (
    DAGNode,
    DAGResult,
    ExecutionPlan,
)

logger = logging.getLogger(__name__)


# ── Condition evaluator ───────────────────────────────────────────────────────


def _evaluate_condition(condition: str, results: dict[str, str]) -> bool:
    """Simple condition evaluator for DAG conditional nodes.

    Supports: "node_id.field == value" and "node_id.field > value"
    """
    try:
        parts = re.split(r"\s*(==|!=|>|<|>=|<=)\s*", condition)
        if len(parts) != 3:
            return True
        ref, op, expected = parts
        node_id, json_field = ref.split(".", 1)
        data = json.loads(results.get(node_id, "{}"))
        actual = data.get(json_field)
        if actual is None:
            return False
        expected_val: Any = int(expected) if expected.isdigit() else expected
        if op == "==":
            return actual == expected_val
        if op == "!=":
            return actual != expected_val
        if op == ">":
            return actual > expected_val
        if op == "<":
            return actual < expected_val
        if op == ">=":
            return actual >= expected_val
        if op == "<=":
            return actual <= expected_val
    except (ValueError, TypeError, KeyError):
        pass
    return True  # default: execute the node


# ── Executor ──────────────────────────────────────────────────────────────────

ToolRunner = Callable[[str, dict], Awaitable[str]]


async def execute_plan(
    plan: ExecutionPlan,
    tool_runner: ToolRunner,
) -> DAGResult:
    """Execute all nodes in the DAG, respecting dependencies and parallelism.

    *tool_runner* is a callable (tool_name, args) -> str that maps
    to the actual DB query functions.
    """
    completed: set[str] = set()
    results: dict[str, str] = {}
    total_tokens = 0

    max_iterations = len(plan.nodes) + 1
    for _ in range(max_iterations):
        ready = plan.ready_nodes(completed)
        if not ready:
            break

        runnable: list[DAGNode] = []
        for node in ready:
            if (
                node.node_type == "conditional"
                and node.condition
                and not _evaluate_condition(node.condition, results)
            ):
                results[node.id] = json.dumps({"skipped": True})
                completed.add(node.id)
                continue
            if node.node_type == "synthesize":
                dep_data = {dep: results.get(dep, "") for dep in node.depends_on}
                results[node.id] = json.dumps(dep_data, separators=(",", ":"))
                total_tokens += count_tokens(results[node.id])
                completed.add(node.id)
                continue
            runnable.append(node)

        if not runnable:
            continue

        async def _run_one(node: DAGNode) -> tuple[str, str]:
            try:
                raw = await tool_runner(node.tool or "", node.args)
                trimmed = budget_tool_result(raw, max_tokens=node.token_budget)
                return node.id, trimmed
            except (ValueError, RuntimeError, OSError, KeyError) as e:
                logger.warning("DAG node %s (%s) failed: %s", node.id, node.tool, e)
                return node.id, json.dumps({"error": str(e)})

        batch = await asyncio.gather(*[_run_one(n) for n in runnable])
        for node_id, result in batch:
            results[node_id] = result
            total_tokens += count_tokens(result)
            completed.add(node_id)

    return DAGResult(node_results=results, plan=plan, total_tokens=total_tokens)
