"""Integration tests for WebSocket endpoints.

Tests cover:
  - /api/ws     — realtime domain event broadcasting
  - /api/ws/chat — AI chat streaming (protocol handshake only; LLM mocked)
"""
import time

import jwt
import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from shared.infrastructure.config import JWT_ALGORITHM, JWT_SECRET

# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_token(
    user_id: str = "user-1",
    org_id: str = "default",
    role: str = "admin",
    name: str = "Test User",
    expired: bool = False,
) -> str:
    payload = {
        "sub": user_id,
        "user_id": user_id,
        "organization_id": org_id,
        "role": role,
        "name": name,
        "exp": int(time.time()) + (-3600 if expired else 3600),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


# ── /api/ws (realtime domain events) ────────────────────────────────────────

class TestRealtimeWebSocket:

    def test_rejects_missing_token(self, client: TestClient):
        with pytest.raises(WebSocketDisconnect, match="4001"), client.websocket_connect("/api/ws"):
            pass

    def test_rejects_expired_token(self, client: TestClient):
        token = _make_token(expired=True)
        with pytest.raises(WebSocketDisconnect, match="4001"), client.websocket_connect(f"/api/ws?token={token}"):
            pass

    def test_accepts_valid_token(self, client: TestClient):
        token = _make_token()
        with client.websocket_connect(f"/api/ws?token={token}") as ws:
            ws.close()

    def test_receives_heartbeat(self, client: TestClient):
        """Connection receives a ping heartbeat within HEARTBEAT_INTERVAL."""
        from unittest.mock import patch
        token = _make_token()
        with patch("shared.api.websocket.HEARTBEAT_INTERVAL", 0.1):
            with client.websocket_connect(f"/api/ws?token={token}") as ws:
                data = ws.receive_json()
                assert data["type"] == "ping"


# ── /api/ws/chat (AI chat streaming) ────────────────────────────────────────

class TestChatWebSocket:

    def test_rejects_missing_token(self, client: TestClient):
        with pytest.raises(WebSocketDisconnect, match="4001"), client.websocket_connect("/api/ws/chat"):
            pass

    def test_rejects_contractor_role(self, client: TestClient):
        token = _make_token(role="contractor")
        with pytest.raises(WebSocketDisconnect, match="4003"):
            with client.websocket_connect(f"/api/ws/chat?token={token}"):
                pass

    def test_accepts_admin_token(self, client: TestClient):
        token = _make_token(role="admin")
        with client.websocket_connect(f"/api/ws/chat?token={token}") as ws:
            ws.close()

    def test_accepts_warehouse_manager_token(self, client: TestClient):
        token = _make_token(role="warehouse_manager")
        with client.websocket_connect(f"/api/ws/chat?token={token}") as ws:
            ws.close()

    def test_empty_message_returns_error(self, client: TestClient):
        token = _make_token()
        with client.websocket_connect(f"/api/ws/chat?token={token}") as ws:
            ws.send_json({"type": "chat", "message": ""})
            resp = ws.receive_json()
            assert resp["type"] == "chat.error"
            assert "Empty" in resp["detail"]

    def test_chat_without_llm_returns_error(self, client: TestClient):
        from unittest.mock import patch
        token = _make_token()
        with patch("assistant.api.ws_chat.ANTHROPIC_AVAILABLE", False), \
             patch("assistant.api.ws_chat.OPENROUTER_AVAILABLE", False):
            with client.websocket_connect(f"/api/ws/chat?token={token}") as ws:
                ws.send_json({
                    "type": "chat",
                    "message": "hello",
                    "session_id": "test-session",
                })
                resp = ws.receive_json()
                assert resp["type"] == "chat.error"
                assert "not configured" in resp["detail"].lower()


# ── Health endpoint verifies WS ─────────────────────────────────────────────

class TestHealthEndpoint:

    def test_ready_includes_websocket_check(self, client: TestClient):
        resp = client.get("/api/ready")
        data = resp.json()
        assert "websocket" in data["checks"]
        ws_check = data["checks"]["websocket"]
        assert ws_check["status"] == "ok"
        assert "/api/ws" in ws_check["endpoints"]
        assert "/api/ws/chat" in ws_check["endpoints"]

    def test_health_returns_ok(self, client: TestClient):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
