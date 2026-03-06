"""WebSocket endpoint for streaming AI chat responses.

Clients send JSON messages over WebSocket, and receive streamed events
as the LLM generates text and calls tools. This replaces the blocking
POST /chat flow with real-time token streaming.

Protocol (client -> server):
    { "type": "chat", "message": "...", "session_id": "...", "agent_type": "auto" }
    { "type": "cancel" }      — abort the current generation
    { "type": "pong" }        — heartbeat response

Protocol (server -> client):
    { "type": "ping" }
    { "type": "chat.status",     "status": "thinking" }
    { "type": "chat.tool_start", "tool": "search_products" }
    { "type": "chat.delta",      "content": "partial text..." }
    { "type": "chat.done",       "response": "...", "agent": "...",
      "tool_calls": [...], "thinking": [...], "session_id": "...",
      "usage": {...} }
    { "type": "chat.error",      "detail": "..." }
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid

import jwt
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic_ai import AgentRunResultEvent
from pydantic_ai.messages import (
    FinalResultEvent,
    PartDeltaEvent,
    PartStartEvent,
    TextPart,
    TextPartDelta,
    ToolCallPart,
    ToolCallPartDelta,
)

from assistant.agents.core.deps import AgentDeps
from assistant.agents.core.messages import (
    build_message_history,
    extract_text_history,
    extract_tool_calls,
    extract_tool_calls_detailed,
)
from assistant.agents.core.model_registry import calc_cost, get_model_name
from assistant.agents.core.validators import validate_response
from assistant.agents.unified.agent import _agent
from assistant.application import session_store
from assistant.application.assistant import recall_memory, schedule_memory_extraction
from shared.infrastructure.config import (
    ANTHROPIC_AVAILABLE,
    JWT_ALGORITHM,
    JWT_SECRET,
    OPENROUTER_AVAILABLE,
    SESSION_COST_CAP,
)

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL = 25
_ALLOWED_ROLES = frozenset({"admin", "warehouse_manager"})


def _authenticate(token: str) -> dict | None:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


async def _send(ws: WebSocket, msg: dict) -> bool:
    """Send JSON to client. Returns False if connection is dead."""
    try:
        await ws.send_text(json.dumps(msg))
        return True
    except Exception:
        return False


def mount_chat_websocket(app: FastAPI) -> None:
    """Register the /api/ws/chat WebSocket endpoint."""

    @app.websocket("/api/ws/chat")
    async def ws_chat_endpoint(websocket: WebSocket):
        token = websocket.query_params.get("token", "")
        payload = _authenticate(token)
        if not payload:
            await websocket.close(code=4001, reason="Invalid or expired token")
            return

        org_id = payload.get("organization_id", "default")
        user_id = payload.get("user_id", "")
        user_name = payload.get("name", "")
        role = payload.get("role", "")

        if role not in _ALLOWED_ROLES:
            await websocket.close(code=4003, reason="Insufficient permissions")
            return

        await websocket.accept()
        logger.info("Chat WS connected: user=%s org=%s", user_id, org_id)

        cancel_event: asyncio.Event | None = None
        generation_task: asyncio.Task | None = None

        async def _heartbeat():
            while True:
                await asyncio.sleep(HEARTBEAT_INTERVAL)
                if not await _send(ws, {"type": "ping"}):
                    return

        async def _receiver():
            """Listen for client messages — chat requests and cancellations."""
            nonlocal cancel_event, generation_task
            try:
                while True:
                    raw = await websocket.receive_text()
                    try:
                        msg = json.loads(raw)
                    except (json.JSONDecodeError, TypeError):
                        continue

                    msg_type = msg.get("type")

                    if msg_type == "pong":
                        continue

                    if msg_type == "cancel":
                        logger.debug("Chat WS cancel from user=%s", user_id)
                        if cancel_event:
                            cancel_event.set()
                        if generation_task and not generation_task.done():
                            generation_task.cancel()
                        continue

                    if msg_type == "chat":
                        if generation_task and not generation_task.done():
                            await _send(ws, {
                                "type": "chat.error",
                                "detail": "Already generating a response. Send 'cancel' first.",
                            })
                            continue

                        cancel_event = asyncio.Event()
                        generation_task = asyncio.create_task(
                            _handle_chat(
                                websocket, msg, org_id, user_id, user_name, cancel_event,
                            )
                        )

            except WebSocketDisconnect:
                logger.debug("Chat WS disconnected: user=%s", user_id)
            except Exception as e:
                logger.warning("Chat WS receiver error for user=%s: %s", user_id, e)
            finally:
                if generation_task and not generation_task.done():
                    generation_task.cancel()
                    try:
                        await generation_task
                    except (asyncio.CancelledError, Exception):
                        pass

        ws = websocket
        tasks = [
            asyncio.create_task(_heartbeat()),
            asyncio.create_task(_receiver()),
        ]
        try:
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for t in pending:
                t.cancel()
        except Exception:
            for t in tasks:
                t.cancel()
        finally:
            logger.info("Chat WS closed: user=%s org=%s", user_id, org_id)


async def _handle_chat(
    ws: WebSocket,
    msg: dict,
    org_id: str,
    user_id: str,
    user_name: str,
    cancel_event: asyncio.Event,
) -> None:
    """Process a single chat message with streaming."""
    user_message = (msg.get("message") or "").strip()
    session_id = msg.get("session_id") or str(uuid.uuid4())

    if not user_message:
        await _send(ws, {"type": "chat.error", "detail": "Empty message"})
        return

    if not ANTHROPIC_AVAILABLE and not OPENROUTER_AVAILABLE:
        await _send(ws, {"type": "chat.error", "detail": "AI not configured."})
        return

    if SESSION_COST_CAP > 0 and session_store.get_cost(session_id) >= SESSION_COST_CAP:
        await _send(ws, {
            "type": "chat.done",
            "response": f"This session has reached the ${SESSION_COST_CAP:.2f} AI spend limit. Start a new chat.",
            "tool_calls": [], "thinking": [], "agent": None,
            "session_id": session_id,
            "usage": {"cost_usd": 0, "capped": True, "session_cost_usd": session_store.get_cost(session_id)},
        })
        return

    history = session_store.get_or_create(session_id)
    if not history:
        try:
            memory_ctx = await recall_memory(org_id=org_id, user_id=user_id)
        except Exception as e:
            logger.warning("Memory recall failed for user=%s: %s", user_id, e)
            memory_ctx = ""
        if memory_ctx:
            history = [
                {"role": "user", "content": memory_ctx},
                {"role": "assistant", "content": "Context noted from previous sessions."},
            ]

    deps = AgentDeps(org_id=org_id, user_id=user_id, user_name=user_name)
    msg_history = build_message_history(history)

    await _send(ws, {"type": "chat.status", "status": "thinking"})

    full_text = ""
    tool_calls_seen: list[dict] = []
    agent_label = "unified"

    logger.info("Chat stream started: user=%s session=%s", user_id, session_id)

    try:
        async for event in _agent.run_stream_events(
            user_message,
            message_history=msg_history,
            deps=deps,
        ):
            if cancel_event.is_set():
                logger.info("Chat stream cancelled: user=%s session=%s", user_id, session_id)
                break

            if isinstance(event, PartStartEvent):
                if isinstance(event.part, ToolCallPart):
                    tool_name = event.part.tool_name
                    tool_calls_seen.append({"tool": tool_name})
                    await _send(ws, {"type": "chat.tool_start", "tool": tool_name})
                elif isinstance(event.part, TextPart):
                    if event.part.content:
                        full_text += event.part.content
                        await _send(ws, {"type": "chat.delta", "content": event.part.content})

            elif isinstance(event, PartDeltaEvent):
                if isinstance(event.delta, TextPartDelta):
                    chunk = event.delta.content_delta
                    if chunk:
                        full_text += chunk
                        await _send(ws, {"type": "chat.delta", "content": chunk})

            elif isinstance(event, FinalResultEvent):
                pass

            elif isinstance(event, AgentRunResultEvent):
                result = event.result
                response_text = result.output if isinstance(result.output, str) else str(result.output)

                if not full_text:
                    full_text = response_text

                model_name = get_model_name(f"agent:{agent_label}")
                usage = result.usage()
                cost = calc_cost(model_name, usage)

                all_msgs = result.all_messages()
                tool_calls_final = extract_tool_calls(all_msgs)
                tool_calls_det = extract_tool_calls_detailed(all_msgs)
                text_history = extract_text_history(all_msgs)

                validate_response(user_message, response_text, tool_calls_final, tool_calls_det)

                turn_cost = cost
                if text_history:
                    new_history = text_history
                else:
                    new_history = list(history or [])
                    new_history.append({"role": "user", "content": user_message})
                    new_history.append({"role": "assistant", "content": full_text})

                session_store.update(session_id, new_history, cost_usd=turn_cost)

                if len(new_history) % 8 == 0:
                    schedule_memory_extraction(
                        org_id=org_id, user_id=user_id,
                        session_id=session_id, history=new_history,
                    )

                logger.info(
                    "Chat stream done: user=%s session=%s cost=%.4f tokens=%d+%d",
                    user_id, session_id, cost, usage.input_tokens, usage.output_tokens,
                )

                await _send(ws, {
                    "type": "chat.done",
                    "response": full_text,
                    "agent": agent_label,
                    "tool_calls": tool_calls_final,
                    "thinking": [],
                    "session_id": session_id,
                    "usage": {
                        "cost_usd": cost,
                        "input_tokens": usage.input_tokens,
                        "output_tokens": usage.output_tokens,
                        "model": model_name,
                        "session_cost_usd": session_store.get_cost(session_id),
                    },
                })
                return

        if cancel_event.is_set():
            response = full_text or "Generation cancelled."
            _save_turn(session_id, history, user_message, response)
            await _send(ws, {
                "type": "chat.done",
                "response": response,
                "agent": agent_label,
                "tool_calls": tool_calls_seen,
                "thinking": [],
                "session_id": session_id,
                "usage": {"cost_usd": 0, "session_cost_usd": session_store.get_cost(session_id)},
                "cancelled": True,
            })
        elif full_text:
            _save_turn(session_id, history, user_message, full_text)
            await _send(ws, {
                "type": "chat.done",
                "response": full_text,
                "agent": agent_label,
                "tool_calls": tool_calls_seen,
                "thinking": [],
                "session_id": session_id,
                "usage": {"cost_usd": 0, "session_cost_usd": session_store.get_cost(session_id)},
            })

    except asyncio.CancelledError:
        logger.debug("Chat generation task cancelled: session=%s", session_id)
        if full_text:
            _save_turn(session_id, history, user_message, full_text)
            await _send(ws, {
                "type": "chat.done",
                "response": full_text,
                "agent": agent_label,
                "tool_calls": tool_calls_seen,
                "thinking": [],
                "session_id": session_id,
                "usage": {"cost_usd": 0, "session_cost_usd": session_store.get_cost(session_id)},
                "cancelled": True,
            })
    except Exception as e:
        logger.error("Chat stream error for user=%s session=%s: %s", user_id, session_id, e, exc_info=True)
        await _send(ws, {"type": "chat.error", "detail": "Something went wrong. Please try again."})


def _save_turn(session_id: str, history: list[dict] | None, user_msg: str, assistant_msg: str) -> None:
    """Persist a user+assistant turn to the session store."""
    new_history = list(history or [])
    new_history.append({"role": "user", "content": user_msg})
    new_history.append({"role": "assistant", "content": assistant_msg})
    session_store.update(session_id, new_history, cost_usd=0)
