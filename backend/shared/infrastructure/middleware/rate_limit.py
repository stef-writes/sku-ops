"""Rate limiting using slowapi.

Configurable per endpoint group via environment variables.
Disabled in the test environment to avoid flaky tests.
"""
from __future__ import annotations

import os

from fastapi import FastAPI
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

_AUTH_LIMIT = os.environ.get("RATE_LIMIT_AUTH", "10/minute")
_CHAT_LIMIT = os.environ.get("RATE_LIMIT_CHAT", "30/minute")
_API_LIMIT = os.environ.get("RATE_LIMIT_API", "120/minute")

limiter = Limiter(key_func=get_remote_address, default_limits=[_API_LIMIT])


def setup_rate_limiting(app: FastAPI) -> None:
    """Attach the limiter to the app and register the error handler."""
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]


# Decorators for use in route modules:
#   from shared.infrastructure.middleware.rate_limit import auth_limit, chat_limit
#   @router.post("/login")
#   @auth_limit
#   async def login(...): ...

def auth_limit(func):
    """5-10/min rate limit for authentication endpoints."""
    return limiter.limit(_AUTH_LIMIT)(func)


def chat_limit(func):
    """20-30/min rate limit for AI chat endpoints."""
    return limiter.limit(_CHAT_LIMIT)(func)
