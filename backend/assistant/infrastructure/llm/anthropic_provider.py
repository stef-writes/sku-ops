"""Direct Anthropic SDK provider adapter — used when OpenRouter is not configured."""

from __future__ import annotations

import logging
from typing import Any

from assistant.infrastructure.llm.catalog import get_model_pricing

logger = logging.getLogger(__name__)


class AnthropicProvider:
    """LLMProvider backed by the Anthropic Python SDK directly."""

    def __init__(self, api_key: str, default_model: str = "claude-sonnet-4-6"):
        self._api_key = api_key
        self._default_model = default_model

    @property
    def provider_name(self) -> str:
        return "anthropic"

    @property
    def available(self) -> bool:
        return bool(self._api_key)

    def build_model(self, model_id: str) -> Any:
        bare = self._strip_provider_prefix(model_id)
        return f"anthropic:{bare}"

    def estimate_cost(
        self,
        model_id: str,
        input_tokens: int,
        output_tokens: int,
    ) -> float:
        pricing = get_model_pricing(model_id)
        if not pricing:
            return 0.0
        return round(
            (
                input_tokens * pricing["input_price_per_m"]
                + output_tokens * pricing["output_price_per_m"]
            )
            / 1_000_000,
            6,
        )

    def get_raw_client(self) -> Any:
        try:
            import anthropic

            return anthropic.Anthropic(api_key=self._api_key)
        except ImportError:
            logger.warning("anthropic package not installed. Run: pip install anthropic")
            return None

    @staticmethod
    def _strip_provider_prefix(model_id: str) -> str:
        """'anthropic/claude-sonnet-4-6' -> 'claude-sonnet-4-6'"""
        if "/" in model_id:
            return model_id.split("/", 1)[1]
        return model_id
