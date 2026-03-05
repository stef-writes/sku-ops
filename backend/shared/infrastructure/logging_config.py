"""Structured logging — JSON in deployed environments, pretty in development.

Usage in server.py:
    from shared.infrastructure.logging_config import setup_logging
    setup_logging()

All log records automatically include request_id / user_id / org_id when
the request_id middleware has set them in contextvars.
"""
from __future__ import annotations

import logging
import os
import sys
from contextvars import ContextVar

_BaseJsonFormatter: type
try:
    from pythonjsonlogger.json import JsonFormatter
    _BaseJsonFormatter = JsonFormatter
except ImportError:
    from pythonjsonlogger import jsonlogger
    _BaseJsonFormatter = jsonlogger.JsonFormatter

# ── Context vars (set by request_id middleware and agent orchestration) ────────

request_id_var: ContextVar[str] = ContextVar("request_id", default="")
user_id_var: ContextVar[str] = ContextVar("user_id", default="")
org_id_var: ContextVar[str] = ContextVar("org_id", default="")
trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")
agent_name_var: ContextVar[str] = ContextVar("agent_name", default="")
operation_var: ContextVar[str] = ContextVar("operation", default="")


# ── Custom JSON formatter ─────────────────────────────────────────────────────

class ContextJsonFormatter(_BaseJsonFormatter):
    """Injects request context into every JSON log line."""

    def add_fields(self, log_record: dict, record: logging.LogRecord, message_dict: dict) -> None:
        super().add_fields(log_record, record, message_dict)
        log_record["level"] = record.levelname
        log_record["logger"] = record.name
        rid = request_id_var.get("")
        if rid:
            log_record["request_id"] = rid
        uid = user_id_var.get("")
        if uid:
            log_record["user_id"] = uid
        oid = org_id_var.get("")
        if oid:
            log_record["org_id"] = oid
        tid = trace_id_var.get("")
        if tid:
            log_record["trace_id"] = tid
        agent = agent_name_var.get("")
        if agent:
            log_record["agent_name"] = agent
        op = operation_var.get("")
        if op:
            log_record["operation"] = op


# ── Pretty formatter for development ─────────────────────────────────────────

class DevFormatter(logging.Formatter):
    """Human-readable colored output for local development."""

    COLORS = {
        "DEBUG": "\033[36m",     # cyan
        "INFO": "\033[32m",      # green
        "WARNING": "\033[33m",   # yellow
        "ERROR": "\033[31m",     # red
        "CRITICAL": "\033[1;31m",  # bold red
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, "")
        rid = request_id_var.get("")
        tid = trace_id_var.get("")
        agent = agent_name_var.get("")
        parts = []
        if rid:
            parts.append(rid[:8])
        if tid:
            parts.append(f"t:{tid}")
        if agent:
            parts.append(agent)
        prefix = f"[{' '.join(parts)}] " if parts else ""
        msg = super().format(record)
        return f"{color}{prefix}{msg}{self.RESET}"


# ── Setup ─────────────────────────────────────────────────────────────────────

def setup_logging() -> None:
    """Configure root logger. Call once at startup before any other logging."""
    from shared.infrastructure.config import is_deployed

    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)

    # Clear any existing handlers (e.g. from basicConfig)
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)

    formatter: logging.Formatter
    if is_deployed:
        formatter = ContextJsonFormatter(
            fmt="%(asctime)s %(level)s %(logger)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    else:
        formatter = DevFormatter(
            fmt="%(asctime)s %(name)-25s %(levelname)-7s %(message)s",
            datefmt="%H:%M:%S",
        )

    handler.setFormatter(formatter)
    root.addHandler(handler)

    # Quiet noisy third-party loggers
    for name in ("uvicorn.access", "httpcore", "httpx", "asyncio"):
        logging.getLogger(name).setLevel(logging.WARNING)
