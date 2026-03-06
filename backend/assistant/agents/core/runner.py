"""Agent execution — run loop with retry/backoff, error classification, and run logging."""
import asyncio
import logging
import random
import time
from enum import Enum

from assistant.agents.core.contracts import AgentConfig, AgentResult, UsageInfo
from assistant.agents.core.messages import (
    extract_text_history,
    extract_tool_calls,
    extract_tool_calls_detailed,
)
from assistant.agents.core.model_registry import calc_cost, get_model_name
from assistant.agents.core.validators import validate_response
from assistant.infrastructure.agent_run_repo import log_agent_run
from shared.infrastructure.config import ANTHROPIC_AVAILABLE, OPENROUTER_AVAILABLE
from shared.infrastructure.logging_config import agent_name_var, operation_var, trace_id_var

logger = logging.getLogger(__name__)

AGENT_TIMEOUT_SECONDS = 45
_MAX_RETRIES = 5
_BASE_DELAY = 1.0   # seconds
_MAX_DELAY = 30.0   # seconds


# ── Config-driven model settings ──────────────────────────────────────────────

def build_model_settings(config: AgentConfig | None, mode: str = "fast") -> dict | None:
    """Build PydanticAI model_settings from an AgentConfig.

    Returns None — no special settings needed in the simplified architecture.
    Deep mode uses a different model via model_registry, not thinking budget.
    """
    return None


def get_agent_timeout(config: AgentConfig | None) -> int:
    """Return timeout seconds from config or global default."""
    if config and config.retry.timeout_seconds:
        return config.retry.timeout_seconds
    return AGENT_TIMEOUT_SECONDS


# ── Error classification ─────────────────────────────────────────────────────

class _ErrorKind(str, Enum):
    RATE_LIMIT  = "rate_limit"
    TIMEOUT     = "timeout"
    NETWORK     = "network"
    SERVER      = "server"
    MODEL_ERROR = "model_error"
    AUTH        = "auth"
    VALIDATION  = "validation"
    UNKNOWN     = "unknown"


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
    """Exponential backoff with jitter. Honours Retry-After when present."""
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
    agent_label: str = "",
    session_id: str = "",
    mode: str = "fast",
):
    """Run a PydanticAI agent with retry/backoff, error classification, and run logging.

    Every invocation (success or failure) is logged to the agent_runs table
    via fire-and-forget background task.
    """
    trace_id = getattr(deps, "trace_id", "")
    if trace_id:
        trace_id_var.set(trace_id)
    agent_name_var.set(agent_name)
    operation_var.set("agent_run")

    active_settings = model_settings
    t0 = time.monotonic()
    attempts = 0

    async def _run(settings):
        return await asyncio.wait_for(
            agent.run(
                user_message,
                message_history=msg_history,
                deps=deps,
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
                agent_label=agent_label,
                session_id=session_id, org_id=getattr(deps, "org_id", ""),
                user_id=getattr(deps, "user_id", ""),
                mode=mode, duration_ms=duration_ms, attempts=attempts,
            )
            return result
        except TimeoutError:
            last_exc = RuntimeError(f"{agent_name} timed out after {timeout_seconds}s")
            kind, retriable, retry_after = _ErrorKind.TIMEOUT, True, None
        except Exception as e:
            last_exc = e
            kind, retriable, retry_after = _classify(e)

        if not retriable:
            logger.error(f"{agent_name} non-retriable {kind} on attempt {attempt + 1}: {last_exc}")
            _log_failure(
                user_message=user_message, agent_name=agent_name,
                agent_label=agent_label,
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
        agent_label=agent_label,
        session_id=session_id, org_id=getattr(deps, "org_id", ""),
        user_id=getattr(deps, "user_id", ""),
        mode=mode, duration_ms=int((time.monotonic() - t0) * 1000),
        attempts=attempts, error=str(last_exc),
        error_kind=_classify(last_exc)[0].value,
    )
    raise last_exc


# ── Run logging (fire-and-forget) ────────────────────────────────────────────

def _log_success(result, *, user_message, agent_name, agent_label="", session_id, org_id, user_id, mode, duration_ms, attempts):
    usage = result.usage()
    label = agent_label or agent_name.split(":")[0].lower().replace("agent", "").strip() or "inventory"
    model_name = get_model_name(f"agent:{label}")
    cost = calc_cost(model_name, usage)
    tool_calls = extract_tool_calls_detailed(result.all_messages())
    response_text = result.output if isinstance(result.output, str) else str(result.output)

    async def _write():
        try:
            await log_agent_run(
                session_id=session_id, org_id=org_id, user_id=user_id,
                agent_name=agent_name, model=model_name, mode=mode,
                user_message=user_message, response_text=response_text,
                tool_calls=tool_calls,
                input_tokens=usage.input_tokens, output_tokens=usage.output_tokens,
                cost_usd=cost, duration_ms=duration_ms, attempts=attempts,
            )
        except Exception as e:
            logger.warning(f"Failed to log agent run: {e}")

    asyncio.create_task(_write())


def _log_failure(*, user_message, agent_name, agent_label="", session_id, org_id, user_id, mode, duration_ms, attempts, error, error_kind):
    label = agent_label or agent_name.split(":")[0].lower().replace("agent", "").strip() or "inventory"
    model_name = get_model_name(f"agent:{label}")

    async def _write():
        try:
            await log_agent_run(
                session_id=session_id, org_id=org_id, user_id=user_id,
                agent_name=agent_name, model=model_name, mode=mode,
                user_message=user_message, response_text="",
                tool_calls=[], input_tokens=0, output_tokens=0,
                cost_usd=0.0, duration_ms=duration_ms, attempts=attempts,
                error=error, error_kind=error_kind,
            )
        except Exception as e:
            logger.warning(f"Failed to log agent run failure: {e}")

    asyncio.create_task(_write())


# ── Specialist runner (no reflection re-run) ──────────────────────────────────

async def run_specialist(
    agent,
    user_message: str,
    *,
    msg_history,
    deps,
    model_settings: dict | None = None,
    agent_name: str = "agent",
    agent_label: str = "inventory",
    session_id: str = "",
    mode: str = "fast",
    history: list[dict] | None = None,
    config: AgentConfig | None = None,
):
    """Run an agent, validate for logging only (no re-run), package result.

    Standard run cycle for all specialist agents:
    1. Run the agent with tools (with retry/backoff)
    2. Run validators for quality scoring (logged, not acted on)
    3. Package the result dict
    """
    if not ANTHROPIC_AVAILABLE and not OPENROUTER_AVAILABLE:
        return {
            "response": f"{agent_name} requires ANTHROPIC_API_KEY or OPENROUTER_API_KEY.",
            "tool_calls": [], "history": [], "thinking": [],
            "agent": agent_label,
        }

    timeout = get_agent_timeout(config)

    try:
        result = await run_agent(
            agent, user_message,
            msg_history=msg_history, deps=deps,
            model_settings=model_settings,
            timeout_seconds=timeout,
            agent_name=agent_name, agent_label=agent_label,
            session_id=session_id, mode=mode,
        )
    except Exception as e:
        logger.error(f"{agent_name} failed: {e}")
        return {
            "response": "I ran into an issue. Please try again in a moment.",
            "tool_calls": [], "history": history or [], "thinking": [],
            "agent": agent_label,
        }

    response_text = result.output if isinstance(result.output, str) else str(result.output)
    model_name = get_model_name(f"agent:{agent_label}")
    usage = result.usage()
    cost = calc_cost(model_name, usage)

    tool_calls_final = extract_tool_calls(result.all_messages())
    tool_calls_det = extract_tool_calls_detailed(result.all_messages())
    text_history = extract_text_history(result.all_messages())

    validation = validate_response(user_message, response_text, tool_calls_final, tool_calls_det)
    validation_dict = {
        "passed": validation.passed,
        "failures": validation.failures,
        "scores": validation.scores,
    }

    agent_result = AgentResult(
        agent=agent_label,
        response=response_text,
        tool_calls=tool_calls_final,
        tool_calls_detailed=tool_calls_det,
        history=text_history,
        usage=UsageInfo(
            cost_usd=cost,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            model=model_name,
        ),
        validation=validation_dict,
    )

    return agent_result.to_dict()
