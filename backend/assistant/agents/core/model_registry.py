"""Model registry — maps task types to models.

Thin adapter over the LLM infrastructure package.
Agent tasks use AGENT_PRIMARY_MODEL (from models.yaml / env) by default.

Env-var overrides still work:
    MODEL_REGISTRY_AGENT_INVENTORY=anthropic/claude-opus-4-6
"""

from __future__ import annotations

import logging
import os

from assistant.infrastructure.llm import get_model as _llm_get_model
from assistant.infrastructure.llm.cost import calc_cost as _cost_calc
from shared.infrastructure.config import AGENT_PRIMARY_MODEL, INFRA_SYNTHESIS_MODEL

logger = logging.getLogger(__name__)

# ── Per-task model assignments ────────────────────────────────────────────────
# Agent tasks inherit AGENT_PRIMARY_MODEL (resolved from models.yaml / env).
# Only non-agent tasks get a separate default.


def _agent_model_id() -> str:
    """Return the configured primary model in OpenRouter slash format."""
    m = AGENT_PRIMARY_MODEL
    if ":" in m and "/" not in m:
        provider, _, model = m.partition(":")
        return f"{provider}/{model}"
    return m


def _synthesis_model_id() -> str:
    m = INFRA_SYNTHESIS_MODEL
    if ":" in m and "/" not in m:
        provider, _, model = m.partition(":")
        return f"{provider}/{model}"
    return m


_DEFAULTS: dict[str, str] = {
    "agent:unified": _agent_model_id(),
    "agent:inventory": _agent_model_id(),
    "agent:ops": _agent_model_id(),
    "agent:finance": _agent_model_id(),
    "infra:synthesis": _synthesis_model_id(),
}


def _resolve(task: str) -> str:
    """Return the model identifier for *task*, checking env overrides first."""
    env_key = "MODEL_REGISTRY_" + task.replace(":", "_").replace(".", "_").upper()
    override = os.environ.get(env_key, "").strip()
    if override:
        return override
    return _DEFAULTS.get(task, _agent_model_id())


def get_model_name(task: str) -> str:
    """Return a pydantic-ai compatible model identifier string for a task.

    Converts OpenRouter slash format (anthropic/model) to pydantic-ai colon
    format (anthropic:model) so Agent() can accept it without an active provider.
    """
    raw = _resolve(task)
    # OpenRouter uses "provider/model", pydantic-ai uses "provider:model"
    if "/" in raw and ":" not in raw:
        provider, _, model = raw.partition("/")
        return f"{provider}:{model}"
    return raw


def get_model(task: str):
    """Return a PydanticAI-compatible model for *task*.

    Falls back to get_model_name() string if init_llm() has not been called yet
    (e.g. during module-level agent construction before lifespan starts).
    PydanticAI can resolve provider:model strings via its own SDK.
    """
    model_name = _resolve(task)
    try:
        return _llm_get_model(model_name)
    except RuntimeError:
        logger.debug("LLM provider not yet initialized, falling back to model name string")
        return get_model_name(task)


def calc_cost(task_or_model: str, usage) -> float:
    """Estimate cost in USD from a PydanticAI Usage object."""
    model = _resolve(task_or_model) if ":" in task_or_model else task_or_model
    inp = getattr(usage, "input_tokens", 0) or 0
    out = getattr(usage, "output_tokens", 0) or 0
    try:
        return _cost_calc(model, inp, out)
    except (RuntimeError, ValueError, TypeError, KeyError, AttributeError):
        return 0.0
