"""LLM provider protocol — interface contract for OpenRouter, Anthropic, and stub adapters.

Mirrors the pattern in shared/infrastructure/db/protocol.py: a runtime-checkable
Protocol that each provider adapter must satisfy.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class LLMProvider(Protocol):
    """Abstraction over LLM API providers (OpenRouter, Anthropic direct, stub)."""

    @property
    def provider_name(self) -> str:
        """Human-readable provider identifier (e.g. 'openrouter', 'anthropic', 'stub')."""
        ...

    @property
    def available(self) -> bool:
        """Whether this provider is configured and ready to serve requests."""
        ...

    def build_model(self, model_id: str) -> Any:
        """Return a PydanticAI-compatible model object for the given model identifier.

        For OpenRouter: returns an OpenAIModel pointed at the gateway.
        For Anthropic direct: returns a PydanticAI-native model string.
        For stub: returns a test double.
        """
        ...

    def estimate_cost(
        self,
        model_id: str,
        input_tokens: int,
        output_tokens: int,
    ) -> float:
        """Estimate cost in USD for the given token counts on *model_id*."""
        ...

    def get_raw_client(self) -> Any:
        """Return the underlying SDK client for non-agent uses (OCR, enrichment).

        Returns None if the provider doesn't support raw client access.
        """
        ...

    def generate_text(
        self,
        prompt: str,
        system_instruction: str | None,
        model_id: str,
    ) -> str | None:
        """Generate text from prompt. Used by workflows, enrichment. Returns None on failure."""
        ...
