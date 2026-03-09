"""Security headers middleware.

Adds defense-in-depth HTTP headers to every response.
HSTS is only added in deployed environments (staging/production).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from shared.infrastructure.config import is_deployed

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response

_COMMON_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "0",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(self), microphone=(), geolocation=()",
    "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; media-src 'self'; frame-ancestors 'none'",
}

_HSTS = "max-age=63072000; includeSubDomains; preload"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        for header, value in _COMMON_HEADERS.items():
            response.headers.setdefault(header, value)
        if is_deployed:
            response.headers.setdefault("Strict-Transport-Security", _HSTS)
        return response
