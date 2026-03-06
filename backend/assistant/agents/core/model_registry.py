"""Model registry — maps task types to models.

Thin adapter over the LLM infrastructure package.

Mode-based model selection:
  - Default (fast): Haiku for all agents
  - Deep: Sonnet for all agents

Env-var overrides still work:
    MODEL_REGISTRY_AGENT_INVENTORY=anthropic/claude-opus-4-6
"""
from __future__ import annotations

import logging
import os

from assistant.infrastructure.llm import get_model as _llm_get_model
from assistant.infrastructure.llm.cost import calc_cost as _cost_calc
from shared.infrastructure.config import AGENT_PRIMARY_MODEL

logger = logging.getLogger(__name__)

# ── Per-task model assignments ────────────────────────────────────────────────

_DEFAULTS: dict[str, str] = {
    "agent:unified":         "anthropic/claude-haiku-4-5",
    "agent:unified:deep":    "anthropic/claude-sonnet-4-6",
    "agent:inventory":       "anthropic/claude-haiku-4-5",
    "agent:ops":             "anthropic/claude-haiku-4-5",
    "agent:finance":         "anthropic/claude-haiku-4-5",
    "agent:inventory:deep":  "anthropic/claude-sonnet-4-6",
    "agent:ops:deep":        "anthropic/claude-sonnet-4-6",
    "agent:finance:deep":    "anthropic/claude-sonnet-4-6",
    "infra:synthesis":       "meta-llama/llama-3.3-70b-instruct",
}


def _resolve(task: str) -> str:
    """Return the model identifier for *task*, checking env overrides first."""
    env_key = "MODEL_REGISTRY_" + task.replace(":", "_").replace(".", "_").upper()
    override = os.environ.get(env_key, "").strip()
    if override:
        return override
    return _DEFAULTS.get(task, _DEFAULTS["agent:inventory"])


def get_model_name(task: str) -> str:
    """Return the raw model identifier string for a task."""
    return _resolve(task)


def get_model(task: str):
    """Return a PydanticAI-compatible model for *task*.

    Falls back to AGENT_PRIMARY_MODEL if init_llm() has not been called yet.
    """
    model_name = _resolve(task)
    try:
        return _llm_get_model(model_name)
    except RuntimeError:
        logger.debug("LLM provider not yet initialized, using AGENT_PRIMARY_MODEL fallback")
        return AGENT_PRIMARY_MODEL


def calc_cost(task_or_model: str, usage) -> float:
    """Estimate cost in USD from a PydanticAI Usage object."""
    model = _resolve(task_or_model) if ":" in task_or_model else task_or_model
    inp = getattr(usage, "input_tokens", 0) or 0
    out = getattr(usage, "output_tokens", 0) or 0
    try:
        return _cost_calc(model, inp, out)
    except Exception:
        return 0.0
