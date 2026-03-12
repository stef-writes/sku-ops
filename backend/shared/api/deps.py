"""Shared dependency aliases for FastAPI route handlers.

IMPORTANT — runtime imports only, never TYPE_CHECKING:
These are not pure type aliases. Each carries a ``Depends(...)`` call that
FastAPI must inspect at import time to wire up dependency injection. If you
move these imports into an ``if TYPE_CHECKING:`` block (even at Ruff's
suggestion via TC001), FastAPI will see an unresolved forward reference and
fall back to treating the parameter as a plain query param, returning 422
instead of 401 for unauthenticated requests.

All api/** files therefore suppress TC001/TC002/TC003 in pyproject.toml.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from identity.api.auth_deps import get_current_user, require_role
from shared.kernel.types import CurrentUser

CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
AdminDep = Annotated[CurrentUser, Depends(require_role("admin"))]
