"""Org settings and Xero OAuth state — application-layer facade.

Safe for cross-context import. Other contexts call these functions
instead of reaching into finance infrastructure directly.
"""

from __future__ import annotations

from finance.domain.xero_settings import XeroSettings
from finance.infrastructure.oauth_state_repo import (
    pop_oauth_state as _pop_state,
)
from finance.infrastructure.oauth_state_repo import (
    save_oauth_state as _save_state,
)
from finance.infrastructure.org_settings_repo import (
    clear_xero_tokens as _clear,
)
from finance.infrastructure.org_settings_repo import (
    get_org_settings as _get,
)
from finance.infrastructure.org_settings_repo import (
    upsert_org_settings as _upsert,
)


async def get_org_settings():
    return await _get()


async def get_xero_settings() -> XeroSettings:
    """Return org settings projected to the XeroSettings shape.

    All Xero integration callers need this projection. Centralising it here
    means callers never touch OrgSettings directly and never perform the
    model_validate(model_dump()) cast themselves.
    """
    settings = await _get()
    return XeroSettings.model_validate(settings.model_dump())


async def upsert_org_settings(settings):
    return await _upsert(settings)


async def clear_xero_tokens() -> None:
    await _clear()


async def save_oauth_state(state: str) -> None:
    await _save_state(state)


async def pop_oauth_state(state: str) -> str | None:
    return await _pop_state(state)
