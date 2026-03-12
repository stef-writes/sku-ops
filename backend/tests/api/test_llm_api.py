"""API tests for LLM health, chat status, and assistant endpoints."""

from unittest.mock import patch

import pytest

from tests.helpers.auth import admin_headers


class TestHealthAI:
    """Test /health/ai endpoint."""

    def test_ai_health_unavailable_without_key(self, client):
        with patch("shared.api.health.ANTHROPIC_AVAILABLE", False):
            with patch("shared.api.health.LLM_SETUP_URL", "https://console.anthropic.com/"):
                response = client.get("/api/health/ai")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "unavailable"
        assert "ANTHROPIC_API_KEY" in data["detail"]
        assert "anthropic.com" in data["detail"]


class TestChatStatus:
    """Test /chat/status endpoint (requires auth)."""

    def test_chat_status_requires_auth(self, client):
        response = client.get("/api/chat/status")
        assert response.status_code in (401, 403)

    @pytest.mark.usefixtures("_db")
    @pytest.mark.asyncio
    async def test_chat_status_unavailable_without_key(self, client):
        headers = admin_headers()
        with patch("assistant.api.chat.ANTHROPIC_AVAILABLE", False):
            with patch("assistant.api.chat.LLM_SETUP_URL", "https://console.anthropic.com/"):
                response = client.get("/api/chat/status", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["available"] is False
        assert data["provider"] is None
        assert data["setup_url"] == "https://console.anthropic.com/"

    @pytest.mark.usefixtures("_db")
    @pytest.mark.asyncio
    async def test_chat_status_available_when_configured(self, client):
        headers = admin_headers()
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

    @pytest.mark.usefixtures("_db")
    async def test_chat_returns_setup_message_without_key(self):
        from assistant.application.assistant import chat

        with patch("assistant.application.assistant.ANTHROPIC_AVAILABLE", False):
            result = await chat("How many products?", history=None)
        assert "ANTHROPIC_API_KEY" in result["response"] or "Anthropic" in result["response"]
        assert result["tool_calls"] == []
