"""Org settings and Xero OAuth state — application-layer facade.

Safe for cross-context import. Other contexts call these functions
instead of reaching into finance infrastructure directly.
"""

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


async def get_org_settings(org_id: str):
    return await _get(org_id)


async def upsert_org_settings(settings):
    return await _upsert(settings)


async def clear_xero_tokens(org_id: str) -> None:
    await _clear(org_id)


async def save_oauth_state(state: str, org_id: str) -> None:
    await _save_state(state, org_id)


async def pop_oauth_state(state: str) -> str | None:
    return await _pop_state(state)
