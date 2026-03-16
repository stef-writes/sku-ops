"""OpenRouter provider adapter — routes to any model via the OpenRouter gateway."""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

logger = logging.getLogger(__name__)


class OpenRouterProvider:
    """LLMProvider backed by the OpenRouter unified gateway."""

    def __init__(self, api_key: str, base_url: str):
        self._api_key = api_key
        self._base_url = base_url

    @property
    def provider_name(self) -> str:
        return "openrouter"

    @property
    def available(self) -> bool:
        return bool(self._api_key)

    def build_model(self, model_id: str) -> Any:
        return self._cached_model(model_id)

    @lru_cache(maxsize=32)
    def _cached_model(self, model_id: str) -> Any:
        from pydantic_ai.models.openai import OpenAIModel
        from pydantic_ai.providers.openai import OpenAIProvider

        provider = OpenAIProvider(api_key=self._api_key, base_url=self._base_url)
        return OpenAIModel(model_id, provider=provider)

    def estimate_cost(
        self,
        model_id: str,
        input_tokens: int,
        output_tokens: int,
    ) -> float:
        return _calc(model_id, input_tokens, output_tokens)

    def get_raw_client(self) -> Any:
        from openai import AsyncOpenAI

        return AsyncOpenAI(api_key=self._api_key, base_url=self._base_url)

    def generate_text(
        self,
        prompt: str,
        system_instruction: str | None,
        model_id: str,
    ) -> str | None:
        from openai import OpenAI

        client = OpenAI(api_key=self._api_key, base_url=self._base_url)
        openrouter_model = model_id.replace(":", "/") if ":" in model_id else model_id
        try:
            messages = []
            if system_instruction:
                messages.append({"role": "system", "content": system_instruction})
            messages.append({"role": "user", "content": prompt})
            resp = client.chat.completions.create(
                model=openrouter_model,
                messages=messages,
                max_tokens=4096,
            )
            if resp.choices and resp.choices[0].message.content:
                return resp.choices[0].message.content
            return None
        except Exception as e:
            logger.warning("OpenRouter generate_text failed: %s", e)
            return None


def _calc(model_id: str, input_tokens: int, output_tokens: int) -> float:
    from assistant.infrastructure.llm.catalog import get_model_pricing

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
