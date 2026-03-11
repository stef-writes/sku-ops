"""Core DAG data structures shared by templates and executor."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DAGNode:
    id: str
    node_type: str  # "tool_call" | "synthesize" | "conditional"
    tool: str | None = None
    args: dict = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)
    token_budget: int = 500
    condition: str | None = None  # e.g. "search.count > 0"


@dataclass
class ExecutionPlan:
    nodes: dict[str, DAGNode] = field(default_factory=dict)
    template_name: str = ""

    def ready_nodes(self, completed: set[str]) -> list[DAGNode]:
        """Nodes whose dependencies are all satisfied — safe to run in parallel."""
        return [
            n
            for n in self.nodes.values()
            if n.id not in completed and all(d in completed for d in n.depends_on)
        ]

    @property
    def synthesis_node(self) -> DAGNode | None:
        """The final synthesis node (if any)."""
        for n in self.nodes.values():
            if n.node_type == "synthesize":
                return n
        return None


@dataclass
class DAGResult:
    node_results: dict[str, str]
    plan: ExecutionPlan
    total_tokens: int = 0
