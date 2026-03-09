"""Prometheus metrics — HTTP request counters, histograms, and /metrics endpoint.

Metrics collected:
    http_requests_total            — Counter[method, endpoint, status]
    http_request_duration_seconds  — Histogram[method, endpoint]
"""
from __future__ import annotations

import logging
import os
import re
import time
from typing import TYPE_CHECKING

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

if TYPE_CHECKING:
    from fastapi import FastAPI, Request

logger = logging.getLogger(__name__)


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
