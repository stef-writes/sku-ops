"""Agent contracts — typed models for the agent system.

Defines the interfaces that agents and the orchestrator share.
Pure data models with no side effects; safe to import anywhere.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ── Agent configuration ───────────────────────────────────────────────────────


@dataclass
class RetryConfig:
    max_retries: int = 3
    timeout_seconds: int = 45
    backoff_base: float = 1.0


@dataclass
class AgentConfig:
    """Declarative agent definition — loaded from YAML, one per agent."""

    id: str
    description: str = ""
    domains: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    max_output_tokens: int = 4000
    temperature: float = 0.0
    retry: RetryConfig = field(default_factory=RetryConfig)


# ── Agent result types ────────────────────────────────────────────────────────


@dataclass
class UsageInfo:
    cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""
    tier: str = ""


@dataclass
class AgentResult:
    """Typed output from any agent run — replaces raw dict returns."""

    agent: str
    response: str
    tool_calls: list[dict] = field(default_factory=list)
    tool_calls_detailed: list[dict] = field(default_factory=list)
    thinking: list[str] = field(default_factory=list)
    history: list[dict] = field(default_factory=list)
    usage: UsageInfo = field(default_factory=UsageInfo)
    confidence: float = 1.0
    validation: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to the dict shape expected by the API layer / frontend."""
        result: dict[str, Any] = {
            "response": self.response,
            "tool_calls": self.tool_calls,
            "thinking": self.thinking,
            "history": self.history,
            "agent": self.agent,
            "usage": {
                "cost_usd": self.usage.cost_usd,
                "input_tokens": self.usage.input_tokens,
                "output_tokens": self.usage.output_tokens,
                "model": self.usage.model,
            },
        }
        if self.validation is not None:
            result["validation"] = self.validation
        return result
