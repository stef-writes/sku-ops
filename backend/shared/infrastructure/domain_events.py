"""Domain event dispatcher — in-process, post-commit, with idempotency + retry.

Bounded contexts register handlers at import time via the ``@on`` decorator.
Application-layer use cases call ``await dispatch(event)`` after their
transaction commits. Each handler runs in its own try/except so one failure
does not block others.

Handlers decorated with ``@idempotent`` are deduplicated via the
``processed_events`` table. Handlers decorated with ``@retryable`` get
automatic retry with exponential backoff on failure.
"""

from __future__ import annotations

import asyncio
import functools
import logging
import time
from collections import defaultdict
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, TypeVar

from shared.kernel.domain_events import DomainEvent

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=DomainEvent)

Handler = Callable[[Any], Awaitable[None]]

_handlers: dict[type, list[Handler]] = defaultdict(list)

_RETRYABLE_ATTR = "_retryable_max_retries"
_IDEMPOTENT_ATTR = "_idempotent"

# Prometheus counters — populated lazily to tolerate missing prometheus_client.
_events_dispatched_total: Any = None
_handler_errors_total: Any = None


def _ensure_metrics() -> None:
    """One-time init of Prometheus counters. No-op if prometheus_client is absent."""
    global _events_dispatched_total, _handler_errors_total
    if _events_dispatched_total is not None:
        return
    try:
        from prometheus_client import Counter

        _events_dispatched_total = Counter(
            "domain_events_dispatched_total",
            "Total domain events dispatched",
            ["event_type"],
        )
        _handler_errors_total = Counter(
            "domain_event_handler_errors_total",
            "Domain event handler failures",
            ["event_type", "handler"],
        )
    except ImportError:
        _events_dispatched_total = False


def on(*event_types: type[DomainEvent]):
    """Decorator to register a handler for one or more domain event types.

    Usage::

        @on(WithdrawalCreated)
        async def handle_withdrawal_created(event: WithdrawalCreated) -> None: ...


        @on(WithdrawalCreated, ReturnCreated)
        async def handle_sale_event(event: DomainEvent) -> None: ...
    """

    def decorator(fn: Handler) -> Handler:
        for et in event_types:
            _handlers[et].append(fn)
        return fn

    return decorator


# ── Idempotency and retry decorators ──────────────────────────────────────────


def idempotent(fn: Handler) -> Handler:
    """Mark a handler as idempotent — skip if (event_id, handler) was already processed."""

    @functools.wraps(fn)
    async def wrapper(event: DomainEvent) -> None:
        handler_key = f"{fn.__module__}.{fn.__qualname__}"
        if await _already_processed(event.event_id, handler_key):
            logger.debug("Skipping duplicate event_id=%s for %s", event.event_id, handler_key)
            return
        await fn(event)
        await _mark_processed(event.event_id, handler_key, type(event).__name__)

    setattr(wrapper, _IDEMPOTENT_ATTR, True)
    return wrapper


def retryable(max_retries: int = 2, base_delay: float = 0.1):
    """Mark a handler for automatic retry with exponential backoff on failure."""

    def decorator(fn: Handler) -> Handler:
        setattr(fn, _RETRYABLE_ATTR, max_retries)
        fn._retryable_base_delay = base_delay
        return fn

    return decorator


async def _already_processed(event_id: str, handler_name: str) -> bool:
    """Check the processed_events table for a prior run."""
    try:
        from shared.infrastructure.database import get_connection

        conn = get_connection()
        cursor = await conn.execute(
            "SELECT 1 FROM processed_events WHERE event_id = $1 AND handler_name = $2",
            (event_id, handler_name),
        )
        return (await cursor.fetchone()) is not None
    except Exception:
        logger.debug("processed_events lookup failed, treating as not processed", exc_info=True)
        return False


async def _mark_processed(event_id: str, handler_name: str, event_type: str) -> None:
    """Record a successful handler execution for future dedup."""
    try:
        from shared.infrastructure.database import get_connection

        conn = get_connection()
        await conn.execute(
            "INSERT INTO processed_events (event_id, handler_name, event_type, processed_at) "
            "VALUES ($1, $2, $3, $4) ON CONFLICT DO NOTHING",
            (event_id, handler_name, event_type, datetime.now(UTC).isoformat()),
        )
        await conn.commit()
    except Exception:
        logger.debug("processed_events insert failed", exc_info=True)


# ── Dispatch ──────────────────────────────────────────────────────────────────


async def _run_handler(handler: Handler, event: DomainEvent) -> bool:
    """Run a single handler, respecting its @retryable setting.

    Returns True on success, False if all attempts exhausted.
    """
    max_retries = getattr(handler, _RETRYABLE_ATTR, 0)
    base_delay = getattr(handler, "_retryable_base_delay", 0.1)

    for attempt in range(max_retries + 1):
        try:
            await handler(event)
            return True
        except Exception:
            if attempt == max_retries:
                logger.exception(
                    "Handler %s.%s failed for %s after %d attempt(s)",
                    handler.__module__,
                    handler.__qualname__,
                    type(event).__name__,
                    max_retries + 1,
                )
                return False
            delay = base_delay * (2**attempt)
            logger.warning(
                "Handler %s.%s retry %d/%d for %s (delay=%.2fs)",
                handler.__module__,
                handler.__qualname__,
                attempt + 1,
                max_retries,
                type(event).__name__,
                delay,
            )
            await asyncio.sleep(delay)
    return False


async def dispatch(event: DomainEvent) -> None:
    """Dispatch a domain event to all registered handlers.

    Handlers run sequentially. Retryable handlers get automatic retry with
    exponential backoff. Each handler's failure is logged and swallowed so
    downstream handlers still execute.
    """
    event_type = type(event).__name__
    handlers = _handlers.get(type(event), [])

    _ensure_metrics()
    if _events_dispatched_total and _events_dispatched_total is not False:
        _events_dispatched_total.labels(event_type=event_type).inc()

    if not handlers:
        logger.debug(
            "domain_event_dispatched event_type=%s handler_count=0 ok=0 failed=0",
            event_type,
        )
        return

    start = time.monotonic()
    ok = 0
    failed = 0
    for handler in handlers:
        success = await _run_handler(handler, event)
        if success:
            ok += 1
        else:
            failed += 1
            handler_name = f"{handler.__module__}.{handler.__qualname__}"
            logger.exception(
                "Domain event handler %s failed for %s",
                handler_name,
                event_type,
            )
            if _handler_errors_total and _handler_errors_total is not False:
                _handler_errors_total.labels(event_type=event_type, handler=handler_name).inc()

    elapsed_ms = round((time.monotonic() - start) * 1000, 1)
    logger.info(
        "domain_event_dispatched event_type=%s handler_count=%d ok=%d failed=%d duration_ms=%.1f",
        event_type,
        len(handlers),
        ok,
        failed,
        elapsed_ms,
    )


def clear_handlers() -> None:
    """Remove all registered handlers. Only for use in tests."""
    _handlers.clear()
