"""Canonical tool registry — single source of truth for all agent tool functions.

Every tool that agents, DAG, and lookups can invoke is registered here once.
Consumers resolve tools by canonical name or (domain, lookup_key) pair.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)

ToolFn = Callable[..., Awaitable[str]]


@dataclass(frozen=True)
class ToolEntry:
    name: str
    domain: str
    fn: ToolFn
    takes_args: bool = True
    lookup_key: str | None = None


_TOOLS: dict[str, ToolEntry] = {}
_LOOKUP_INDEX: dict[tuple[str, str], ToolEntry] = {}


def register(
    name: str,
    domain: str,
    fn: ToolFn,
    *,
    takes_args: bool = True,
    lookup_key: str | None = None,
) -> None:
    """Register a tool. Called at import time by each agent package."""
    entry = ToolEntry(name=name, domain=domain, fn=fn, takes_args=takes_args, lookup_key=lookup_key)
    _TOOLS[name] = entry
    if lookup_key:
        _LOOKUP_INDEX[(domain, lookup_key)] = entry


def get(name: str) -> ToolEntry | None:
    """Look up a tool by its canonical name (e.g. 'search_products')."""
    return _TOOLS.get(name)


def get_by_lookup_key(domain: str, key: str) -> ToolEntry | None:
    """Look up a tool by (domain, lookup_key) pair — used by the lookup engine."""
    return _LOOKUP_INDEX.get((domain, key))


def all_tools() -> dict[str, ToolEntry]:
    """Return the full registry (read-only snapshot)."""
    return dict(_TOOLS)


def names_for_domain(domain: str) -> set[str]:
    """Return canonical names of all tools in a domain."""
    return {e.name for e in _TOOLS.values() if e.domain == domain}


async def run_tool(name: str, args: dict) -> str:
    """Execute a tool by canonical name. Used by DAG executor and assistant."""
    entry = _TOOLS.get(name)
    if not entry:
        return f'{{"error": "unknown tool: {name}"}}'
    try:
        if entry.takes_args:
            result = await entry.fn(args)
        else:
            result = await entry.fn()
        return result if isinstance(result, str) else str(result)
    except (ValueError, RuntimeError, OSError, KeyError) as e:
        logger.warning("Tool %s failed: %s", name, e)
        return f'{{"error": "{e}"}}'


def init_tools() -> None:
    """Import agent tool modules so they self-register. Call once at startup."""
    if _TOOLS:
        return
    import assistant.agents.finance.tools
    import assistant.agents.inventory.tools
    import assistant.agents.ops.tools  # noqa: F401
