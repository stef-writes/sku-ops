"""LLM package — drop-in provider abstraction for all LLM access.

Public API (mirrors the pattern in shared/infrastructure/db/__init__.py):
    init_llm()       — call once at startup (in server.py lifespan)
    get_provider()   — returns the active LLMProvider
    get_model()      — shortcut: build a PydanticAI model for a given model_id
    estimate_cost()  — shortcut: estimate USD cost for token counts

The backend (OpenRouter vs Anthropic direct vs stub) is selected automatically
from environment configuration.
"""
from __future__ import annotations

import logging
from typing import Any

from assistant.infrastructure.llm.protocol import LLMProvider

logger = logging.getLogger(__name__)

_provider: LLMProvider | None = None


def init_llm() -> None:
    """Select the LLM provider based on environment config. Call once at startup."""
    global _provider

    from shared.infrastructure.config import (
        AGENT_PRIMARY_MODEL,
        ANTHROPIC_API_KEY,
        ANTHROPIC_AVAILABLE,
        OPENROUTER_API_KEY,
        OPENROUTER_AVAILABLE,
        OPENROUTER_BASE_URL,
        is_test,
    )

    if is_test:
        from assistant.infrastructure.llm.stub import StubProvider
        _provider = StubProvider()
        logger.info("LLM provider: stub (test mode)")
        return

    if OPENROUTER_AVAILABLE:
        from assistant.infrastructure.llm.openrouter import OpenRouterProvider
        _provider = OpenRouterProvider(OPENROUTER_API_KEY, OPENROUTER_BASE_URL)
        logger.info("LLM provider: openrouter (%s)", OPENROUTER_BASE_URL)
        return

    if ANTHROPIC_AVAILABLE:
        from assistant.infrastructure.llm.anthropic_provider import AnthropicProvider
        _provider = AnthropicProvider(ANTHROPIC_API_KEY, AGENT_PRIMARY_MODEL)
        logger.info("LLM provider: anthropic (direct SDK)")
        return

    from assistant.infrastructure.llm.stub import StubProvider
    _provider = StubProvider()
    logger.warning("No LLM API keys configured — using stub provider")


def get_provider() -> LLMProvider:
    """Return the active LLM provider. Raises if init_llm() was not called."""
    if _provider is None:
        raise RuntimeError("LLM not initialized. Call init_llm() at startup.")
    return _provider


def get_model(model_id: str) -> Any:
    """Build a PydanticAI-compatible model for *model_id* via the active provider."""
    return get_provider().build_model(model_id)


def estimate_cost(model_id: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate cost in USD for the given token counts."""
    return get_provider().estimate_cost(model_id, input_tokens, output_tokens)
