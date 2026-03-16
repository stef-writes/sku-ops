"""Workflow base primitives — parallel fetch and synthesis.

Shared by fixed DAG workflows. No workflow-specific logic.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING

from assistant.agents.core.model_registry import get_model_name
from assistant.agents.tools.registry import init_tools, run_tool
from assistant.application.llm import generate_text

if TYPE_CHECKING:
    from collections.abc import Callable

    from assistant.application.workflows.types import FetchSpec

logger = logging.getLogger(__name__)


def _is_json(s: str) -> bool:
    s = (s or "").strip()
    return s.startswith(("{", "["))


async def run_parallel_fetch(specs: list[FetchSpec]) -> dict:
    """Fetch multiple tools in parallel and return aggregated dict keyed by result_key.

    Calls init_tools(), runs each spec via run_tool(), parses JSON responses,
    and assembles into a dict. Non-JSON responses become {}.
    """
    init_tools()
    tasks = [run_tool(s.tool_name, s.args) for s in specs]
    results = await asyncio.gather(*tasks)
    out: dict = {}
    for spec, raw in zip(specs, results, strict=False):
        if _is_json(raw):
            try:
                out[spec.result_key] = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                out[spec.result_key] = {}
        else:
            out[spec.result_key] = {}
    return out


async def run_synthesis(
    data: dict,
    system_prompt: str,
    build_prompt: Callable[[dict], str],
    fallback_fn: Callable[[dict], str],
) -> str:
    """Synthesize raw data into markdown via LLM, with fallback on failure.

    Uses infra:synthesis model from models.yaml / env.
    """
    prompt = build_prompt(data)
    synthesis_model = get_model_name("infra:synthesis")
    synthesized = await asyncio.to_thread(generate_text, prompt, system_prompt, synthesis_model)
    if synthesized and synthesized.strip():
        return synthesized.strip()
    return fallback_fn(data)
