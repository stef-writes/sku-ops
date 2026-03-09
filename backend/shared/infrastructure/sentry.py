"""Sentry error tracking — captures unhandled exceptions and slow transactions.

Enabled when SENTRY_DSN is set.  Each event is enriched with request_id,
org_id, and user_id from the request context.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _sentry_before_send(event: dict, _hint: dict) -> dict:
    """Enrich every Sentry event with request correlation context."""
    from shared.infrastructure.logging_config import (
        org_id_var,
        request_id_var,
        user_id_var,
    )

    rid = request_id_var.get("")
    uid = user_id_var.get("")
    oid = org_id_var.get("")

    tags = event.setdefault("tags", {})
    if rid:
        tags["request_id"] = rid
    if oid:
        tags["org_id"] = oid

    if uid:
        event.setdefault("user", {})["id"] = uid

    return event


def setup_sentry() -> None:
    """Initialize Sentry if SENTRY_DSN is configured."""
    from shared.infrastructure.config import _ENV, SENTRY_DSN

    if not SENTRY_DSN:
        return

    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration

        sentry_sdk.init(
            dsn=SENTRY_DSN,
            environment=_ENV,
            traces_sample_rate=0.2,
            profiles_sample_rate=0.1,
            integrations=[
                StarletteIntegration(transaction_style="endpoint"),
                FastApiIntegration(transaction_style="endpoint"),
            ],
            send_default_pii=False,
            before_send=_sentry_before_send,
        )
        logger.info("Sentry initialized (env=%s)", _ENV)
    except ImportError:
        logger.warning("sentry_sdk not installed — Sentry disabled despite SENTRY_DSN being set")
    except Exception:
        logger.exception("Failed to initialize Sentry")
