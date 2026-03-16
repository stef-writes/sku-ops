"""Security headers middleware.

Adds defense-in-depth HTTP headers to every response.
HSTS is only added in production.
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
    # CSP intentionally omitted: this is a JSON/WebSocket API, not an HTML document.
    # CSP on API responses has no browser effect and can interfere with debugging.
    # CSP belongs in vercel.json on the frontend where it protects the actual document.
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
