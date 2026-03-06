"""Authenticated WebSocket endpoint for realtime event broadcasting.

Clients connect with their JWT token and receive domain events scoped to
their organization. Contractor connections are filtered to only receive
events relevant to their role.

The endpoint is mounted directly on the FastAPI app (not behind the /api
router) because FastAPI WebSocket routes are registered differently from
HTTP routes. The ``mount_websocket`` helper wires it up in server.py.
"""
from __future__ import annotations

import asyncio
import json
import logging

import jwt
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from shared.infrastructure import event_hub
from shared.infrastructure.config import JWT_ALGORITHM, JWT_SECRET

logger = logging.getLogger(__name__)

CONTRACTOR_VISIBLE_EVENTS = frozenset({
    "material_request.created",
    "material_request.processed",
    "withdrawal.created",
    "withdrawal.updated",
})

HEARTBEAT_INTERVAL = 30


def _authenticate(token: str) -> dict | None:
    """Validate JWT and return payload, or None on failure."""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


def _should_deliver(event: event_hub.Event, org_id: str, role: str, user_id: str) -> bool:
    if event.org_id != org_id:
        return False
    if event.user_id and event.user_id != user_id:
        return False
    if role == "contractor" and event.type not in CONTRACTOR_VISIBLE_EVENTS:
        return False
    return True


def mount_websocket(app: FastAPI) -> None:
    """Register the /api/ws WebSocket endpoint on the given app."""

    @app.websocket("/api/ws")
    async def ws_endpoint(websocket: WebSocket):
        token = websocket.query_params.get("token", "")
        payload = _authenticate(token)
        if not payload:
            await websocket.close(code=4001, reason="Invalid or expired token")
            return

        org_id = payload.get("organization_id", "default")
        role = payload.get("role", "")
        user_id = payload.get("user_id", "")
        await websocket.accept()

        queue = event_hub.subscribe()
        try:
            await _relay_loop(websocket, queue, org_id, role, user_id)
        finally:
            event_hub.unsubscribe(queue)


async def _relay_loop(
    websocket: WebSocket,
    queue: asyncio.Queue[event_hub.Event],
    org_id: str,
    role: str,
    user_id: str = "",
) -> None:
    """Forward hub events to the client, with periodic heartbeats."""
    async def _sender():
        while True:
            event = await queue.get()
            if not _should_deliver(event, org_id, role, user_id):
                continue
            msg = {"type": event.type, **event.data}
            try:
                await websocket.send_text(json.dumps(msg))
            except Exception:
                return

    async def _heartbeat():
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            try:
                await websocket.send_text(json.dumps({"type": "ping"}))
            except Exception:
                return

    async def _receiver():
        """Consume client messages to detect disconnects."""
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass

    tasks = [
        asyncio.create_task(_sender()),
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
