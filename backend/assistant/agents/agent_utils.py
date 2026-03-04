"""Shared utilities for all specialist agents."""
import asyncio
import json
import logging
import random
import time
from enum import Enum

from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from shared.infrastructure.config import AGENT_PRIMARY_MODEL

logger = logging.getLogger(__name__)

AGENT_TIMEOUT_SECONDS = 45
_MAX_RETRIES = 5
_BASE_DELAY = 1.0   # seconds
_MAX_DELAY = 30.0   # seconds


# ── Error classification ─────────────────────────────────────────────────────

class _ErrorKind(str, Enum):
    RATE_LIMIT  = "rate_limit"   # 429 — retriable, backoff, honour Retry-After
    TIMEOUT     = "timeout"      # network or wait_for timeout — retriable
    NETWORK     = "network"      # connection errors — retriable
    SERVER      = "server"       # 500/503/overload — retriable
    MODEL_ERROR = "model_error"  # thinking budget, bad model_settings — drop settings + retry
    AUTH        = "auth"         # 401/403 — NOT retriable
    VALIDATION  = "validation"   # 400 — NOT retriable
    UNKNOWN     = "unknown"      # NOT retriable


def _classify(e: Exception) -> tuple[_ErrorKind, bool, float | None]:
    """Return (kind, is_retriable, retry_after_seconds)."""
    s = str(e).lower()
    t = type(e).__name__.lower()

    retry_after: float | None = None
    resp = getattr(e, "response", None)
    if resp is not None:
        hdrs = getattr(resp, "headers", {})
        ra = hdrs.get("retry-after") or hdrs.get("x-ratelimit-reset-requests")
        if ra:
            try:
                retry_after = float(ra)
            except (ValueError, TypeError):
                pass

    if any(k in t for k in ("ratelimit", "rate_limit")) or \
       any(k in s for k in ("rate limit", "429", "too many requests", "ratelimit")):
        return _ErrorKind.RATE_LIMIT, True, retry_after

    if isinstance(e, asyncio.TimeoutError) or "timeout" in t or "timeout" in s:
        return _ErrorKind.TIMEOUT, True, None

    if any(k in t for k in ("connection", "network", "connect")) or \
       any(k in s for k in ("connection error", "network", "socket", "unreachable", "refused", "reset by peer")):
        return _ErrorKind.NETWORK, True, None

    if any(k in s for k in ("500", "502", "503", "529", "overload", "internal server", "service unavailable", "bad gateway")):
        return _ErrorKind.SERVER, True, None

    if any(k in s for k in ("thinking", "budget", "extended thinking", "model_settings")):
        return _ErrorKind.MODEL_ERROR, True, None

    if any(k in t for k in ("auth", "permission")) or \
       any(k in s for k in ("401", "403", "unauthorized", "forbidden", "invalid api key", "authentication")):
        return _ErrorKind.AUTH, False, None

    if any(k in s for k in ("400", "bad request", "invalid request")) or "badrequest" in t:
        return _ErrorKind.VALIDATION, False, None

    return _ErrorKind.UNKNOWN, False, None


async def _backoff(attempt: int, retry_after: float | None) -> None:
    """Exponential backoff with ±25% jitter. Honours Retry-After when present."""
    if retry_after is not None:
        delay = min(retry_after, _MAX_DELAY)
    else:
        delay = min(_BASE_DELAY * (2 ** attempt), _MAX_DELAY)
    jitter = random.uniform(-delay * 0.25, delay * 0.25)
    await asyncio.sleep(max(0.1, delay + jitter))


# ── Agent runner ─────────────────────────────────────────────────────────────

async def run_agent(
    agent,
    user_message: str,
    *,
    msg_history,
    deps,
    model_settings: dict | None = None,
    timeout_seconds: int = AGENT_TIMEOUT_SECONDS,
    agent_name: str = "agent",
    session_id: str = "",
    mode: str = "fast",
):
    """Run a PydanticAI agent with retry/backoff, error classification, and run logging.

    Every invocation (success or failure) is logged to the agent_runs table
    via fire-and-forget background task.
    """
    active_settings = model_settings
    t0 = time.monotonic()
    attempts = 0

    async def _run(settings):
        return await asyncio.wait_for(
            agent.run(
                user_message,
                message_history=msg_history,
                deps=deps,
                model=AGENT_PRIMARY_MODEL,
                model_settings=settings or None,
            ),
            timeout=timeout_seconds,
        )

    last_exc: Exception = RuntimeError(f"{agent_name}: no attempts made")

    for attempt in range(_MAX_RETRIES):
        attempts = attempt + 1
        try:
            result = await _run(active_settings)
            duration_ms = int((time.monotonic() - t0) * 1000)
            _log_success(
                result, user_message=user_message, agent_name=agent_name,
                session_id=session_id, org_id=getattr(deps, "org_id", ""),
                user_id=getattr(deps, "user_id", ""),
                mode=mode, duration_ms=duration_ms, attempts=attempts,
            )
            return result
        except asyncio.TimeoutError:
            last_exc = RuntimeError(f"{agent_name} timed out after {timeout_seconds}s")
            kind, retriable, retry_after = _ErrorKind.TIMEOUT, True, None
        except Exception as e:
            last_exc = e
            kind, retriable, retry_after = _classify(e)

        if not retriable:
            logger.error(f"{agent_name} non-retriable {kind} on attempt {attempt + 1}: {last_exc}")
            _log_failure(
                user_message=user_message, agent_name=agent_name,
                session_id=session_id, org_id=getattr(deps, "org_id", ""),
                user_id=getattr(deps, "user_id", ""),
                mode=mode, duration_ms=int((time.monotonic() - t0) * 1000),
                attempts=attempts, error=str(last_exc), error_kind=kind.value,
            )
            raise last_exc

        if active_settings and kind == _ErrorKind.MODEL_ERROR:
            logger.warning(f"{agent_name} model_error with thinking settings, dropping and retrying: {last_exc}")
            active_settings = None
            continue

        if attempt < _MAX_RETRIES - 1:
            logger.warning(f"{agent_name} {kind} on attempt {attempt + 1}/{_MAX_RETRIES}, backing off: {last_exc}")
            await _backoff(attempt, retry_after)
        else:
            logger.warning(f"{agent_name} {kind} on final attempt {_MAX_RETRIES}/{_MAX_RETRIES}: {last_exc}")

    _log_failure(
        user_message=user_message, agent_name=agent_name,
        session_id=session_id, org_id=getattr(deps, "org_id", ""),
        user_id=getattr(deps, "user_id", ""),
        mode=mode, duration_ms=int((time.monotonic() - t0) * 1000),
        attempts=attempts, error=str(last_exc),
        error_kind=_classify(last_exc)[0].value,
    )
    raise last_exc


# ── Run logging (fire-and-forget) ────────────────────────────────────────────

def _log_success(result, *, user_message, agent_name, session_id, org_id, user_id, mode, duration_ms, attempts):
    usage = result.usage()
    cost = calc_cost(AGENT_PRIMARY_MODEL, usage)
    tool_calls = extract_tool_calls_detailed(result.all_messages())
    response_text = result.output if isinstance(result.output, str) else str(result.output)

    async def _write():
        try:
            from assistant.infrastructure.agent_run_repo import log_agent_run
            await log_agent_run(
                session_id=session_id, org_id=org_id, user_id=user_id,
                agent_name=agent_name, model=AGENT_PRIMARY_MODEL, mode=mode,
                user_message=user_message, response_text=response_text,
                tool_calls=tool_calls,
                input_tokens=usage.input_tokens, output_tokens=usage.output_tokens,
                cost_usd=cost, duration_ms=duration_ms, attempts=attempts,
            )
        except Exception as e:
            logger.warning(f"Failed to log agent run: {e}")

    asyncio.create_task(_write())


def _log_failure(*, user_message, agent_name, session_id, org_id, user_id, mode, duration_ms, attempts, error, error_kind):
    async def _write():
        try:
            from assistant.infrastructure.agent_run_repo import log_agent_run
            await log_agent_run(
                session_id=session_id, org_id=org_id, user_id=user_id,
                agent_name=agent_name, model=AGENT_PRIMARY_MODEL, mode=mode,
                user_message=user_message, response_text="",
                tool_calls=[], input_tokens=0, output_tokens=0,
                cost_usd=0.0, duration_ms=duration_ms, attempts=attempts,
                error=error, error_kind=error_kind,
            )
        except Exception as e:
            logger.warning(f"Failed to log agent run failure: {e}")

    asyncio.create_task(_write())


# ── Pricing ───────────────────────────────────────────────────────────────────

_MODEL_PRICING: dict[str, dict[str, float]] = {
    "claude-haiku-4-5":  {"input": 0.80,  "output": 4.00},
    "claude-sonnet-4-6": {"input": 3.00,  "output": 15.00},
    "claude-opus-4-6":   {"input": 15.00, "output": 75.00},
}


def calc_cost(model: str, usage) -> float:
    model = model.split(":", 1)[-1]
    key = next((k for k in _MODEL_PRICING if model.startswith(k)), None)
    if not key:
        return 0.0
    p = _MODEL_PRICING[key]
    return round((usage.input_tokens * p["input"] + usage.output_tokens * p["output"]) / 1_000_000, 6)


# ── History helpers ───────────────────────────────────────────────────────────

def build_message_history(history: list[dict] | None) -> list | None:
    """Convert text-only {role, content} pairs → PydanticAI ModelMessage list."""
    if not history:
        return None
    messages = []
    for h in history:
        content = (h.get("content") or "").strip()
        if not content:
            continue
        if h.get("role") == "user":
            messages.append(ModelRequest(parts=[UserPromptPart(content=content)]))
        else:
            messages.append(ModelResponse(parts=[TextPart(content=content)], model_name=None))
    return messages or None


def extract_text_history(messages) -> list[dict]:
    """Extract text-only turns from PydanticAI all_messages() for session storage."""
    out = []
    for msg in messages:
        if isinstance(msg, ModelRequest):
            for part in msg.parts:
                if isinstance(part, UserPromptPart):
                    text = part.content if isinstance(part.content, str) else ""
                    if text:
                        out.append({"role": "user", "content": text})
        elif isinstance(msg, ModelResponse):
            for part in msg.parts:
                if isinstance(part, TextPart) and part.content:
                    out.append({"role": "assistant", "content": part.content})
    return out


def extract_tool_calls(messages) -> list[dict]:
    """Extract tool call names only (lightweight, for API response)."""
    out = []
    for msg in messages:
        if isinstance(msg, ModelResponse):
            for part in msg.parts:
                if isinstance(part, ToolCallPart):
                    out.append({"tool": part.tool_name})
    return out


def extract_tool_calls_detailed(messages) -> list[dict]:
    """Extract tool calls with arguments and return values for monitoring."""
    # Build a map of tool_call_id → return value from subsequent ModelRequests
    return_map: dict[str, str] = {}
    for msg in messages:
        if isinstance(msg, ModelRequest):
            for part in msg.parts:
                if isinstance(part, ToolReturnPart):
                    ret = part.content if isinstance(part.content, str) else str(part.content)
                    return_map[part.tool_call_id] = ret[:500]

    out = []
    for msg in messages:
        if isinstance(msg, ModelResponse):
            for part in msg.parts:
                if isinstance(part, ToolCallPart):
                    args_raw = part.args
                    if isinstance(args_raw, str):
                        try:
                            args_raw = json.loads(args_raw)
                        except (json.JSONDecodeError, TypeError):
                            pass
                    entry = {
                        "tool": part.tool_name,
                        "args": args_raw,
                        "result_preview": return_map.get(part.tool_call_id, ""),
                    }
                    out.append(entry)
    return out
