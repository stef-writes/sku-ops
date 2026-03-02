"""Tests for Anthropic LLM config, health, and AI features."""
import base64
from unittest.mock import MagicMock, patch

import pytest

# Import after conftest sets ENV
from config import (
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
        from services.llm import generate_text

        with patch("services.llm._get_client", return_value=None):
            result = generate_text("Hello")
        assert result is None

    def test_generate_text_returns_text_when_mocked(self):
        """generate_text returns model output when client is mocked."""
        from services.llm import generate_text

        mock_client = MagicMock()
        mock_client.messages.create.return_value = MagicMock(
            content=[MagicMock(text="Mocked response")]
        )

        with patch("services.llm._get_client", return_value=mock_client):
            result = generate_text("Hello", system_instruction="Be helpful")

        assert result == "Mocked response"
        mock_client.messages.create.assert_called_once()
        call_kw = mock_client.messages.create.call_args[1]
        assert call_kw["model"] == ANTHROPIC_FAST_MODEL
        assert call_kw["system"] == "Be helpful"
        assert call_kw["messages"][0]["content"] == "Hello"

    def test_generate_with_image_raises_without_client(self):
        """generate_with_image raises when LLM not configured."""
        from services.llm import generate_with_image

        with patch("services.llm._get_client", return_value=None):
            with pytest.raises(ValueError, match="LLM not configured"):
                generate_with_image("Describe this", b"\xff\xd8\xfffake-jpeg")

    def test_generate_with_image_succeeds_when_mocked(self):
        """generate_with_image returns model output when client is mocked."""
        from services.llm import generate_with_image

        mock_client = MagicMock()
        mock_client.messages.create.return_value = MagicMock(
            content=[MagicMock(text="A red apple")]
        )

        # Minimal JPEG bytes
        jpeg_bytes = b"\xff\xd8\xff\x00\x00\x00\x00\xff\xd9"

        with patch("services.llm._get_client", return_value=mock_client):
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
        from services.llm import generate_with_pdf

        with patch("services.llm._get_client", return_value=None):
            with pytest.raises(ValueError, match="LLM not configured"):
                generate_with_pdf("Extract items", "/nonexistent.pdf")


class TestChatStatus:
    """Test /chat/status endpoint (requires auth)."""

    def _auth_headers(self, client):
        """Get auth headers using test user token."""
        from auth import create_token

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
        with patch("api.chat.ANTHROPIC_AVAILABLE", False):
            with patch("api.chat.LLM_SETUP_URL", "https://console.anthropic.com/"):
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
        with patch("api.chat.ANTHROPIC_AVAILABLE", True):
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
        from services.assistant import chat

        with patch("services.assistant.ANTHROPIC_AVAILABLE", False):
            result = await chat([], "How many products?")
        assert "ANTHROPIC_API_KEY" in result["response"] or "Anthropic" in result["response"]
        assert result["tool_calls"] == []
        assert result["history"] == []

    async def test_chat_uses_tools_when_mocked(self, db):
        """Chat assistant calls tools when model requests them."""
        from unittest.mock import AsyncMock
        from services.assistant import chat

        # First call: model requests tool_use
        mock_tool_block = MagicMock()
        mock_tool_block.type = "tool_use"
        mock_tool_block.id = "tool-1"
        mock_tool_block.name = "get_inventory_stats"
        mock_tool_block.input = {}
        mock_tool_block.model_dump.return_value = {
            "type": "tool_use",
            "id": "tool-1",
            "name": "get_inventory_stats",
            "input": {},
        }

        tool_use_response = MagicMock()
        tool_use_response.stop_reason = "tool_use"
        tool_use_response.content = [mock_tool_block]

        # Second call: model returns final text
        text_block = MagicMock()
        text_block.text = "You have 0 products in inventory."
        text_block.model_dump.return_value = {"type": "text", "text": text_block.text}
        end_response = MagicMock()
        end_response.stop_reason = "end_turn"
        end_response.content = [text_block]

        mock_client = MagicMock()
        mock_client.messages.create = MagicMock(
            side_effect=[tool_use_response, end_response]
        )

        # Router delegates to inventory agent; bypass the LLM classify call.
        # patch("anthropic.Anthropic") patches the class at the source so any
        # `import anthropic; anthropic.Anthropic(...)` call picks up the mock.
        with patch("services.assistant.ANTHROPIC_AVAILABLE", True), \
             patch("services.agents.router.ANTHROPIC_AVAILABLE", True), \
             patch("services.agents.router.classify", new=AsyncMock(return_value="inventory")), \
             patch("services.agents.inventory.ANTHROPIC_AVAILABLE", True), \
             patch("services.agents.inventory.ANTHROPIC_API_KEY", "test-key"), \
             patch("anthropic.Anthropic", return_value=mock_client):
            result = await chat([], "What's our inventory count?")

        assert result["response"] == "You have 0 products in inventory."
        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["tool"] == "get_inventory_stats"


@pytest.mark.asyncio
class TestUOMClassifier:
    """Test UOM classifier (uses LLM when available)."""

    async def test_classify_uom_returns_default_when_llm_unavailable(self):
        """UOM classifier returns default when generate_text returns None."""
        from services.uom_classifier import classify_uom

        with patch("services.uom_classifier.generate_text", return_value=None):
            result = await classify_uom("Mystery product")
        assert result == {"base_unit": "each", "sell_uom": "each", "pack_qty": 1}

    async def test_classify_uom_uses_llm_when_mocked(self):
        """UOM classifier uses LLM output when available."""
        from services.uom_classifier import classify_uom

        with patch("services.uom_classifier.generate_text", return_value='{"base_unit":"gallon","sell_uom":"gallon","pack_qty":5}'):
            result = await classify_uom("5 Gal Paint")
        assert result["base_unit"] == "gallon"
        assert result["sell_uom"] == "gallon"
        assert result["pack_qty"] == 5
