"""Observability — Prometheus metrics and optional Sentry integration.

Prometheus:
    Exposes /metrics endpoint and collects request metrics via middleware.
    Metrics: http_requests_total, http_request_duration_seconds.

Sentry:
    Enabled when SENTRY_DSN is set. Captures unhandled exceptions and
    slow transactions with FastAPI integration.
"""
from __future__ import annotations

import logging
import os
import re
import time

from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

logger = logging.getLogger(__name__)


# ── Prometheus ────────────────────────────────────────────────────────────────

try:
    from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

    http_requests_total = Counter(
        "http_requests_total",
        "Total HTTP requests",
        ["method", "endpoint", "status"],
    )
    http_request_duration = Histogram(
        "http_request_duration_seconds",
        "HTTP request duration in seconds",
        ["method", "endpoint"],
        buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    )
    _PROMETHEUS_AVAILABLE = True
except ImportError:
    _PROMETHEUS_AVAILABLE = False


_UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE,
)
_NUMERIC_SEGMENT = re.compile(r"/\d+(?=/|$)")


def _normalize_path(path: str) -> str:
    """Replace UUIDs and numeric IDs with placeholders to bound cardinality."""
    path = _UUID_RE.sub(":id", path)
    path = _NUMERIC_SEGMENT.sub("/:id", path)
    return path


class PrometheusMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not _PROMETHEUS_AVAILABLE:
            return await call_next(request)

        start = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - start

        path = _normalize_path(request.url.path)
        method = request.method

        http_requests_total.labels(
            method=method,
            endpoint=path,
            status=response.status_code,
        ).inc()
        http_request_duration.labels(
            method=method,
            endpoint=path,
        ).observe(elapsed)

        return response


_METRICS_TOKEN = os.environ.get("METRICS_TOKEN", "").strip()


def setup_prometheus(app: FastAPI) -> None:
    """Add /metrics endpoint and request metrics middleware.

    When METRICS_TOKEN is set, the /metrics endpoint requires
    ``Authorization: Bearer <token>`` to prevent leaking operational data.
    """
    if not _PROMETHEUS_AVAILABLE:
        logger.info("prometheus_client not installed — metrics disabled")
        return

    app.add_middleware(PrometheusMiddleware)

    @app.get("/metrics", include_in_schema=False)
    async def metrics(request: Request):
        if _METRICS_TOKEN:
            auth = request.headers.get("authorization", "")
            if auth != f"Bearer {_METRICS_TOKEN}":
                return Response(status_code=403, content="Forbidden")
        from starlette.responses import Response as StarletteResponse
        return StarletteResponse(
            content=generate_latest(),
            media_type=CONTENT_TYPE_LATEST,
        )

    logger.info("Prometheus metrics enabled at /metrics%s", " (token-protected)" if _METRICS_TOKEN else "")


# ── Sentry ────────────────────────────────────────────────────────────────────


def _sentry_before_send(event: dict, hint: dict) -> dict:
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
