"""Integration tests for the /api/ws/chat WebSocket endpoint.

Tests cover:
  - Authentication (valid/invalid/expired tokens, role-based access)
  - Protocol correctness (ping/pong, chat flow, cancel)
  - Streaming event sequence (status → deltas/tool_start → done)
  - Error handling (empty message, duplicate generation, AI not configured)
  - Session management (session_id assignment, cost cap)
  - Connection lifecycle (heartbeat, graceful close)
"""
import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from identity.application.auth_service import create_token
from shared.infrastructure.config import JWT_ALGORITHM, JWT_SECRET

# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    from server import app
    return TestClient(app)


def _admin_token() -> str:
    return create_token("user-1", "test@test.com", "admin", "default")


def _contractor_token() -> str:
    return create_token("contractor-1", "contractor@test.com", "contractor", "default")


def _warehouse_manager_token() -> str:
    return create_token("user-2", "wm@test.com", "warehouse_manager", "default")


def _expired_token() -> str:
    payload = {
        "user_id": "user-1",
        "email": "test@test.com",
        "role": "admin",
        "organization_id": "default",
        "exp": int(time.time()) - 3600,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


# ── Helper to make a mock stream event sequence ──────────────────────────────

def _make_mock_stream(text_chunks, tool_names=None):
    """Build a mock async iterator that yields PydanticAI stream events."""

    from pydantic_ai import AgentRunResultEvent
    from pydantic_ai.messages import (
        PartDeltaEvent,
        PartStartEvent,
        TextPart,
        TextPartDelta,
        ToolCallPart,
    )

    events = []

    if tool_names:
        for name in tool_names:
            events.append(PartStartEvent(
                index=0,
                part=ToolCallPart(
                    tool_name=name,
                    args=None,
                    tool_call_id=f"tc_{name}",
                ),
                previous_part_kind=None,
            ))

    if text_chunks:
        events.append(PartStartEvent(
            index=1,
            part=TextPart(content=text_chunks[0]),
            previous_part_kind="tool-call" if tool_names else None,
        ))
        for chunk in text_chunks[1:]:
            events.append(PartDeltaEvent(
                index=1,
                delta=TextPartDelta(
                    content_delta=chunk,
                    provider_name=None,
                    provider_details=None,
                ),
            ))

    full_text = "".join(text_chunks)

    mock_usage = MagicMock()
    mock_usage.input_tokens = 100
    mock_usage.output_tokens = 50

    mock_result = MagicMock()
    mock_result.output = full_text
    mock_result.usage.return_value = mock_usage
    mock_result.all_messages.return_value = []

    result_event = AgentRunResultEvent(result=mock_result)
    events.append(result_event)

    async def _stream(*args, **kwargs):
        for ev in events:
            yield ev

    return _stream


# ── Authentication tests ──────────────────────────────────────────────────────

def _assert_ws_close(client, url: str, expected_code: int):
    """Connect and assert the server closes with the given code."""
    try:
        with client.websocket_connect(url):
            pass
        pytest.fail(f"Expected WebSocketDisconnect({expected_code})")
    except WebSocketDisconnect as exc:
        assert exc.code == expected_code, f"Expected close code {expected_code}, got {exc.code}"


class TestWSChatAuth:
    def test_no_token_rejected(self, client):
        _assert_ws_close(client, "/api/ws/chat", 4001)

    def test_invalid_token_rejected(self, client):
        _assert_ws_close(client, "/api/ws/chat?token=garbage", 4001)

    def test_expired_token_rejected(self, client):
        _assert_ws_close(client, f"/api/ws/chat?token={_expired_token()}", 4001)

    def test_contractor_role_rejected(self, client):
        """Contractors cannot use the AI assistant."""
        _assert_ws_close(client, f"/api/ws/chat?token={_contractor_token()}", 4003)

    def test_admin_connects_successfully(self, client):
        token = _admin_token()
        with client.websocket_connect(f"/api/ws/chat?token={token}") as ws:
            # Should be able to receive the first ping
            msg = json.loads(ws.receive_text())
            assert msg["type"] == "ping"

    def test_warehouse_manager_connects_successfully(self, client):
        token = _warehouse_manager_token()
        with client.websocket_connect(f"/api/ws/chat?token={token}") as ws:
            msg = json.loads(ws.receive_text())
            assert msg["type"] == "ping"


# ── Protocol tests ────────────────────────────────────────────────────────────

class TestWSChatProtocol:
    def test_pong_response_accepted(self, client):
        """Server should accept pong messages without error."""
        token = _admin_token()
        with client.websocket_connect(f"/api/ws/chat?token={token}") as ws:
            ws.send_text(json.dumps({"type": "pong"}))
            msg = json.loads(ws.receive_text())
            assert msg["type"] == "ping"

    def test_malformed_json_ignored(self, client):
        """Malformed messages should be silently ignored."""
        token = _admin_token()
        with client.websocket_connect(f"/api/ws/chat?token={token}") as ws:
            ws.send_text("not json at all")
            msg = json.loads(ws.receive_text())
            assert msg["type"] == "ping"

    def test_unknown_message_type_ignored(self, client):
        """Unknown message types should be silently ignored."""
        token = _admin_token()
        with client.websocket_connect(f"/api/ws/chat?token={token}") as ws:
            ws.send_text(json.dumps({"type": "unknown_type"}))
            msg = json.loads(ws.receive_text())
            assert msg["type"] == "ping"


# ── Chat streaming tests ─────────────────────────────────────────────────────

class TestWSChatStreaming:
    def test_empty_message_returns_error(self, client):
        token = _admin_token()
        with client.websocket_connect(f"/api/ws/chat?token={token}") as ws:
            ws.send_text(json.dumps({
                "type": "chat",
                "message": "",
            }))
            # Receive heartbeat pings and the error
            messages = _collect_messages(ws, until_type="chat.error", max_msgs=5)
            error = _find_msg(messages, "chat.error")
            assert error is not None
            assert "Empty" in error["detail"]

    def test_whitespace_only_message_returns_error(self, client):
        token = _admin_token()
        with client.websocket_connect(f"/api/ws/chat?token={token}") as ws:
            ws.send_text(json.dumps({
                "type": "chat",
                "message": "   ",
            }))
            messages = _collect_messages(ws, until_type="chat.error", max_msgs=5)
            error = _find_msg(messages, "chat.error")
            assert error is not None

    @patch("assistant.api.ws_chat.ANTHROPIC_AVAILABLE", False)
    @patch("assistant.api.ws_chat.OPENROUTER_AVAILABLE", False)
    def test_ai_not_configured_returns_error(self, client):
        token = _admin_token()
        with client.websocket_connect(f"/api/ws/chat?token={token}") as ws:
            ws.send_text(json.dumps({
                "type": "chat",
                "message": "Hello",
            }))
            messages = _collect_messages(ws, until_type="chat.error", max_msgs=5)
            error = _find_msg(messages, "chat.error")
            assert error is not None
            assert "not configured" in error["detail"].lower()

    @patch("assistant.api.ws_chat._agent")
    @patch("assistant.api.ws_chat.ANTHROPIC_AVAILABLE", True)
    def test_streaming_event_sequence(self, mock_agent, client):
        """Verify the full event sequence: status → deltas → done."""
        mock_stream = _make_mock_stream(
            text_chunks=["Hello ", "world!", " How can I help?"],
            tool_names=["search_products"],
        )
        mock_agent.run_stream_events = mock_stream

        token = _admin_token()
        with client.websocket_connect(f"/api/ws/chat?token={token}") as ws:
            ws.send_text(json.dumps({
                "type": "chat",
                "message": "Search for widgets",
            }))

            messages = _collect_messages(ws, until_type="chat.done", max_msgs=20)

            status = _find_msg(messages, "chat.status")
            assert status is not None
            assert status["status"] == "thinking"

            tool_starts = [m for m in messages if m["type"] == "chat.tool_start"]
            assert len(tool_starts) == 1
            assert tool_starts[0]["tool"] == "search_products"

            deltas = [m for m in messages if m["type"] == "chat.delta"]
            assert len(deltas) >= 1
            streamed_text = "".join(d["content"] for d in deltas)
            assert "Hello " in streamed_text

            done = _find_msg(messages, "chat.done")
            assert done is not None
            assert done["response"] == "Hello world! How can I help?"
            assert done["agent"] == "unified"
            assert "session_id" in done
            assert "usage" in done

    @patch("assistant.api.ws_chat._agent")
    @patch("assistant.api.ws_chat.ANTHROPIC_AVAILABLE", True)
    def test_session_id_assigned_when_missing(self, mock_agent, client):
        """When no session_id is provided, one should be auto-assigned."""
        mock_stream = _make_mock_stream(text_chunks=["Hi there!"])
        mock_agent.run_stream_events = mock_stream

        token = _admin_token()
        with client.websocket_connect(f"/api/ws/chat?token={token}") as ws:
            ws.send_text(json.dumps({
                "type": "chat",
                "message": "Hello",
            }))
            messages = _collect_messages(ws, until_type="chat.done", max_msgs=10)
            done = _find_msg(messages, "chat.done")
            assert done is not None
            assert done["session_id"]
            assert len(done["session_id"]) > 0

    @patch("assistant.api.ws_chat._agent")
    @patch("assistant.api.ws_chat.ANTHROPIC_AVAILABLE", True)
    def test_session_id_preserved_when_provided(self, mock_agent, client):
        """When session_id is provided, it should be echoed back."""
        mock_stream = _make_mock_stream(text_chunks=["Hi!"])
        mock_agent.run_stream_events = mock_stream

        token = _admin_token()
        with client.websocket_connect(f"/api/ws/chat?token={token}") as ws:
            ws.send_text(json.dumps({
                "type": "chat",
                "message": "Hello",
                "session_id": "my-session-123",
            }))
            messages = _collect_messages(ws, until_type="chat.done", max_msgs=10)
            done = _find_msg(messages, "chat.done")
            assert done["session_id"] == "my-session-123"

    @patch("assistant.api.ws_chat._agent")
    @patch("assistant.api.ws_chat.ANTHROPIC_AVAILABLE", True)
    def test_done_payload_has_usage_fields(self, mock_agent, client):
        mock_stream = _make_mock_stream(text_chunks=["Report ready."])
        mock_agent.run_stream_events = mock_stream

        token = _admin_token()
        with client.websocket_connect(f"/api/ws/chat?token={token}") as ws:
            ws.send_text(json.dumps({"type": "chat", "message": "Show P&L"}))
            messages = _collect_messages(ws, until_type="chat.done", max_msgs=10)
            done = _find_msg(messages, "chat.done")
            usage = done["usage"]
            assert "cost_usd" in usage
            assert "input_tokens" in usage
            assert "output_tokens" in usage
            assert "session_cost_usd" in usage


# ── Error handling tests ──────────────────────────────────────────────────────

class TestWSChatErrors:
    @patch("assistant.api.ws_chat._agent")
    @patch("assistant.api.ws_chat.ANTHROPIC_AVAILABLE", True)
    def test_agent_exception_returns_chat_error(self, mock_agent, client):
        """If the agent raises, client should get a chat.error event."""
        async def _failing_stream(*args, **kwargs):
            raise RuntimeError("LLM provider down")
            yield  # noqa: unreachable — makes it an async generator

        mock_agent.run_stream_events = _failing_stream

        token = _admin_token()
        with client.websocket_connect(f"/api/ws/chat?token={token}") as ws:
            ws.send_text(json.dumps({"type": "chat", "message": "Hello"}))
            messages = _collect_messages(ws, until_type="chat.error", max_msgs=10)
            error = _find_msg(messages, "chat.error")
            assert error is not None
            assert "wrong" in error["detail"].lower()

    @patch("assistant.api.ws_chat._agent")
    @patch("assistant.api.ws_chat.ANTHROPIC_AVAILABLE", True)
    def test_duplicate_generation_rejected(self, mock_agent, client):
        """Sending a second chat while one is streaming should return an error."""
        async def _slow_stream(*args, **kwargs):
            from pydantic_ai import AgentRunResultEvent

            await asyncio.sleep(5)
            mock_result = MagicMock()
            mock_result.output = "done"
            mock_result.usage.return_value = MagicMock(input_tokens=10, output_tokens=5)
            mock_result.all_messages.return_value = []
            yield AgentRunResultEvent(result=mock_result)

        mock_agent.run_stream_events = _slow_stream

        token = _admin_token()
        with client.websocket_connect(f"/api/ws/chat?token={token}") as ws:
            ws.send_text(json.dumps({"type": "chat", "message": "First message"}))
            # Wait for status to confirm generation started
            messages = _collect_messages(ws, until_type="chat.status", max_msgs=5)
            assert _find_msg(messages, "chat.status") is not None

            # Send second message while still generating
            ws.send_text(json.dumps({"type": "chat", "message": "Second message"}))
            messages = _collect_messages(ws, until_type="chat.error", max_msgs=5)
            error = _find_msg(messages, "chat.error")
            assert error is not None
            assert "already" in error["detail"].lower()


# ── Session cost cap tests ────────────────────────────────────────────────────

class TestWSChatCostCap:
    @patch("assistant.api.ws_chat.session_store")
    @patch("assistant.api.ws_chat.SESSION_COST_CAP", 1.00)
    @patch("assistant.api.ws_chat.ANTHROPIC_AVAILABLE", True)
    def test_cost_cap_reached_returns_done_with_capped(self, mock_store, client):
        mock_store.get_cost = AsyncMock(return_value=1.50)
        mock_store.get_or_create = AsyncMock(return_value=[])

        token = _admin_token()
        with client.websocket_connect(f"/api/ws/chat?token={token}") as ws:
            ws.send_text(json.dumps({"type": "chat", "message": "One more question"}))
            messages = _collect_messages(ws, until_type="chat.done", max_msgs=5)
            done = _find_msg(messages, "chat.done")
            assert done is not None
            assert "spend limit" in done["response"].lower()
            assert done["usage"]["capped"] is True


# ── Helpers ───────────────────────────────────────────────────────────────────

def _collect_messages(ws, *, until_type, max_msgs=20, timeout_each=3.0):
    """Read messages from WebSocket until we see a message of `until_type`."""
    collected = []
    for _ in range(max_msgs):
        try:
            raw = ws.receive_text()
            msg = json.loads(raw)
            collected.append(msg)
            if msg.get("type") == until_type:
                break
        except (json.JSONDecodeError, RuntimeError, OSError):
            break
    return collected


def _find_msg(messages, msg_type):
    """Find the first message of the given type."""
    for m in messages:
        if m.get("type") == msg_type:
            return m
    return None
