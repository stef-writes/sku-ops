"""Org settings application service — safe for cross-context import."""

from identity.infrastructure.oauth_state_repo import (
    pop_oauth_state as _pop_state,
)
from identity.infrastructure.oauth_state_repo import (
    save_oauth_state as _save_state,
)
from identity.infrastructure.org_settings_repo import (
    clear_xero_tokens as _clear,
)
from identity.infrastructure.org_settings_repo import (
    get_org_settings as _get,
)
from identity.infrastructure.org_settings_repo import (
    upsert_org_settings as _upsert,
)


async def get_org_settings():
    return await _get()


async def upsert_org_settings(settings):
    return await _upsert(settings)


async def clear_xero_tokens() -> None:
    await _clear()


async def save_oauth_state(state: str) -> None:
    await _save_state(state)


async def pop_oauth_state(state: str) -> str | None:
    return await _pop_state(state)
