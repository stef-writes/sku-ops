"""Tests for Anthropic LLM config, health, and AI features."""
import base64
from unittest.mock import MagicMock, patch

import pytest

# Import after conftest sets ENV
from shared.infrastructure.config import (
    ANTHROPIC_AVAILABLE,
    ANTHROPIC_API_KEY,
    ANTHROPIC_FAST_MODEL,
    ANTHROPIC_MODEL,
    LLM_SETUP_URL,
)


class TestConfig:
    """Test AI config values."""

    def test_default_models(self):
        """Default models are claude-sonnet-4-6 and claude-haiku-4-5."""
        assert "claude-sonnet" in ANTHROPIC_MODEL
        assert "claude-haiku" in ANTHROPIC_FAST_MODEL

    def test_llm_setup_url(self):
        """Setup URL points to Anthropic console."""
        assert LLM_SETUP_URL == "https://console.anthropic.com/"

    def test_availability_tracks_api_key(self):
        """ANTHROPIC_AVAILABLE is True only when API key is set."""
        # In test env without key, typically False
        assert isinstance(ANTHROPIC_AVAILABLE, bool)
        if not ANTHROPIC_API_KEY:
            assert ANTHROPIC_AVAILABLE is False


class TestHealthAI:
    """Test /health/ai endpoint."""

    def test_ai_health_unavailable_without_key(self, client):
        """Without ANTHROPIC_API_KEY, returns 503 with setup URL."""
        with patch("api.health.ANTHROPIC_AVAILABLE", False):
            with patch("api.health.LLM_SETUP_URL", "https://console.anthropic.com/"):
                response = client.get("/api/health/ai")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "unavailable"
        assert "ANTHROPIC_API_KEY" in data["detail"]
        assert "anthropic.com" in data["detail"]

    def test_ai_health_ok_when_configured(self, client):
        """With Anthropic configured, returns 200 and model info."""
        with patch("api.health.ANTHROPIC_AVAILABLE", True):
            with patch("api.health.ANTHROPIC_MODEL", "claude-sonnet-4-6"):
                response = client.get("/api/health/ai")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["provider"] == "anthropic"
        assert "claude" in data["model"]


class TestLLMService:
    """Test services.llm functions."""

    def test_generate_text_returns_none_without_client(self):
        """generate_text returns None when Anthropic not configured."""
        from assistant.application.llm import generate_text

        with patch("assistant.application.llm._get_client", return_value=None):
            result = generate_text("Hello")
        assert result is None

    def test_generate_text_returns_text_when_mocked(self):
        """generate_text returns model output when client is mocked."""
        from assistant.application.llm import generate_text

        mock_client = MagicMock()
        mock_client.messages.create.return_value = MagicMock(
            content=[MagicMock(text="Mocked response")]
        )

        with patch("assistant.application.llm._get_client", return_value=mock_client):
            result = generate_text("Hello", system_instruction="Be helpful")

        assert result == "Mocked response"
        mock_client.messages.create.assert_called_once()
        call_kw = mock_client.messages.create.call_args[1]
        assert call_kw["model"] == ANTHROPIC_FAST_MODEL
        assert call_kw["system"] == "Be helpful"
        assert call_kw["messages"][0]["content"] == "Hello"

    def test_generate_with_image_raises_without_client(self):
        """generate_with_image raises when LLM not configured."""
        from assistant.application.llm import generate_with_image

        with patch("assistant.application.llm._get_client", return_value=None):
            with pytest.raises(ValueError, match="LLM not configured"):
                generate_with_image("Describe this", b"\xff\xd8\xfffake-jpeg")

    def test_generate_with_image_succeeds_when_mocked(self):
        """generate_with_image returns model output when client is mocked."""
        from assistant.application.llm import generate_with_image

        mock_client = MagicMock()
        mock_client.messages.create.return_value = MagicMock(
            content=[MagicMock(text="A red apple")]
        )

        # Minimal JPEG bytes
        jpeg_bytes = b"\xff\xd8\xff\x00\x00\x00\x00\xff\xd9"

        with patch("assistant.application.llm._get_client", return_value=mock_client):
            result = generate_with_image("What is this?", jpeg_bytes)

        assert result == "A red apple"
        call_kw = mock_client.messages.create.call_args[1]
        assert call_kw["model"] == ANTHROPIC_MODEL
        content = call_kw["messages"][0]["content"]
        assert len(content) == 2  # image + text
        assert content[0]["type"] == "image"
        assert content[0]["source"]["media_type"] == "image/jpeg"
        assert base64.standard_b64decode(content[0]["source"]["data"]) == jpeg_bytes
        assert content[1]["text"] == "What is this?"

    def test_generate_with_pdf_raises_without_client(self):
        """generate_with_pdf raises when LLM not configured."""
        from assistant.application.llm import generate_with_pdf

        with patch("assistant.application.llm._get_client", return_value=None):
            with pytest.raises(ValueError, match="LLM not configured"):
                generate_with_pdf("Extract items", "/nonexistent.pdf")


class TestChatStatus:
    """Test /chat/status endpoint (requires auth)."""

    def _auth_headers(self, client):
        """Get auth headers using test user token."""
        from identity.application.auth_service import create_token

        token = create_token("user-1", "test@test.com", "admin", "default")
        return {"Authorization": f"Bearer {token}"}

    def test_chat_status_requires_auth(self, client):
        """Chat status returns 401/403 without token."""
        response = client.get("/api/chat/status")
        assert response.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_chat_status_unavailable_without_key(self, client, db):
        """Chat status reports available=false when no API key."""
        headers = self._auth_headers(client)
        with patch("assistant.api.chat.ANTHROPIC_AVAILABLE", False):
            with patch("assistant.api.chat.LLM_SETUP_URL", "https://console.anthropic.com/"):
                response = client.get("/api/chat/status", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["available"] is False
        assert data["provider"] is None
        assert data["setup_url"] == "https://console.anthropic.com/"

    @pytest.mark.asyncio
    async def test_chat_status_available_when_configured(self, client, db):
        """Chat status reports available=true when Anthropic configured."""
        headers = self._auth_headers(client)
        with patch("assistant.api.chat.ANTHROPIC_AVAILABLE", True):
            response = client.get("/api/chat/status", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["available"] is True
        assert data["provider"] == "anthropic"
        assert data.get("setup_url") is None


@pytest.mark.asyncio
class TestAssistant:
    """Test chat assistant service."""

    async def test_chat_returns_setup_message_without_key(self, db):
        """When no API key, chat returns setup instructions."""
        from assistant.application.assistant import chat

        with patch("assistant.application.assistant.ANTHROPIC_AVAILABLE", False):
            result = await chat("How many products?", history=None)
        assert "ANTHROPIC_API_KEY" in result["response"] or "Anthropic" in result["response"]
        assert result["tool_calls"] == []

    async def test_chat_dispatches_to_correct_agent(self, db):
        """assistant.chat() dispatches to the correct specialist agent by agent_type."""
        from unittest.mock import AsyncMock
        from assistant.application.assistant import chat

        expected = {
            "response": "You have 0 products in inventory.",
            "tool_calls": [{"tool": "get_inventory_stats"}],
            "thinking": [],
            "history": [],
            "usage": {"cost_usd": 0.0, "model": "claude-haiku-4-5"},
            "agent": "inventory",
        }

        with patch("assistant.application.assistant.ANTHROPIC_AVAILABLE", True), \
             patch("assistant.agents.inventory.run", new=AsyncMock(return_value=expected)):
            result = await chat(
                "What's our inventory count?",
                history=None,
                agent_type="inventory",
            )

        assert result["response"] == "You have 0 products in inventory."
        assert result["agent"] == "inventory"
        assert result["tool_calls"][0]["tool"] == "get_inventory_stats"


@pytest.mark.asyncio
class TestUOMClassifier:
    """Test UOM classifier (uses LLM when available)."""

    async def test_classify_uom_returns_default_when_llm_unavailable(self):
        """UOM classifier returns default when generate_text returns None."""
        from inventory.application.uom_classifier import classify_uom

        with patch("inventory.application.uom_classifier.generate_text", return_value=None):
            result = await classify_uom("Mystery product")
        assert result == {"base_unit": "each", "sell_uom": "each", "pack_qty": 1}

    async def test_classify_uom_uses_llm_when_mocked(self):
        """UOM classifier uses LLM output when available."""
        from inventory.application.uom_classifier import classify_uom

        with patch("inventory.application.uom_classifier.generate_text", return_value='{"base_unit":"gallon","sell_uom":"gallon","pack_qty":5}'):
            result = await classify_uom("5 Gal Paint")
        assert result["base_unit"] == "gallon"
        assert result["sell_uom"] == "gallon"
        assert result["pack_qty"] == 5
