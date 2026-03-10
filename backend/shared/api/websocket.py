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

from kernel.events import CONTRACTOR_VISIBLE_EVENTS, Event
from shared.infrastructure import event_hub
from shared.infrastructure.config import DEFAULT_ORG_ID, JWT_ALGORITHM, JWT_SECRET

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL = 30


def _authenticate(token: str) -> dict | None:
    """Validate JWT and return payload, or None on failure."""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


def _should_deliver(event: Event, org_id: str, role: str, user_id: str) -> bool:
    if event.org_id != org_id:
        return False
    if event.user_id and event.user_id != user_id:
        return False
    return not (role == "contractor" and event.type not in CONTRACTOR_VISIBLE_EVENTS)


def mount_websocket(app: FastAPI) -> None:
    """Register the /api/ws WebSocket endpoint on the given app."""

    @app.websocket("/api/ws")
    async def ws_endpoint(websocket: WebSocket):
        token = websocket.query_params.get("token", "")
        payload = _authenticate(token)
        if not payload:
            await websocket.close(code=4001, reason="Invalid or expired token")
            return

        org_id = payload.get("organization_id", DEFAULT_ORG_ID)
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
    queue: asyncio.Queue[Event],
    org_id: str,
    role: str,
    user_id: str = "",
) -> None:
    """Forward hub events to the client, with periodic heartbeats."""

    async def _sender():
        while True:
            ev = await queue.get()
            if event_hub.is_shutdown(ev):
                logger.info("Subscriber shutdown — closing WebSocket")
                return
            if not _should_deliver(ev, org_id, role, user_id):
                continue
            msg = {"type": ev.type, **ev.data}
            try:
                await websocket.send_text(json.dumps(msg))
            except (RuntimeError, OSError):
                return

    async def _heartbeat():
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            try:
                await websocket.send_text(json.dumps({"type": "ping"}))
            except (RuntimeError, OSError):
                return

    async def _receiver():
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
        _done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for t in pending:
            t.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
    except (RuntimeError, OSError):
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
