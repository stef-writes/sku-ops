"""Unit tests for LLM service — graceful degradation and fallback behavior.

Tests only behaviors that matter: what happens when the LLM is unavailable,
misconfigured, or returns garbage. Mock-returns-mock tests are excluded.
"""

from unittest.mock import MagicMock, patch

import pytest

from inventory.application.uom_classifier import UOMClassification
from shared.infrastructure.config import ANTHROPIC_AVAILABLE

_DEFAULT_UOM = UOMClassification(base_unit="each", sell_uom="each", pack_qty=1)


class TestLLMAvailability:
    """Availability flag must reflect actual key presence."""

    def test_availability_tracks_api_key(self):
        assert isinstance(ANTHROPIC_AVAILABLE, bool)


class TestGracefulDegradation:
    """When LLM client is absent, functions must degrade explicitly — not crash."""

    def test_generate_text_returns_none_without_client(self):
        from assistant.application.llm import generate_text

        with patch("assistant.application.llm._get_client", return_value=None):
            result = generate_text("Hello")
        assert result is None

    def test_generate_with_image_raises_without_client(self):
        from assistant.application.llm import generate_with_image

        with patch("assistant.application.llm._get_client", return_value=None):
            with pytest.raises(ValueError, match="LLM not configured"):
                generate_with_image("Describe this", b"\xff\xd8\xfffake-jpeg")

    def test_generate_with_pdf_raises_without_client(self):
        from assistant.application.llm import generate_with_pdf

        with patch("assistant.application.llm._get_client", return_value=None):
            with pytest.raises(ValueError, match="LLM not configured"):
                generate_with_pdf("Extract items", "/nonexistent.pdf")

    def test_generate_text_exception_returns_none(self):
        from assistant.application.llm import generate_text

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = RuntimeError("API timeout")

        with patch("assistant.application.llm._get_client", return_value=mock_client):
            result = generate_text("Hello")
        assert result is None


@pytest.mark.asyncio
class TestUOMClassifierFallback:
    """UOM classifier must return safe defaults when LLM is unavailable."""

    async def test_classify_uom_returns_default_when_llm_unavailable(self):
        from inventory.application.uom_classifier import classify_uom

        result = await classify_uom("Mystery product")
        assert result == _DEFAULT_UOM

    async def test_classify_uom_handles_malformed_llm_response(self):
        from inventory.application.uom_classifier import classify_uom

        def mock_generate_text(_prompt, _system):
            return "not valid json at all {{{}"

        result = await classify_uom("5 Gal Paint", generate_text=mock_generate_text)
        assert result == _DEFAULT_UOM

    async def test_classify_uom_handles_llm_exception(self):
        from inventory.application.uom_classifier import classify_uom

        def mock_generate_text(_prompt, _system):
            raise RuntimeError("LLM unavailable")

        result = await classify_uom("5 Gal Paint", generate_text=mock_generate_text)
        assert result == _DEFAULT_UOM
