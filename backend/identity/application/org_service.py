"""Org settings application service — safe for cross-context import."""
from identity.infrastructure.org_settings_repo import (
    get_org_settings as _get,
    upsert_org_settings as _upsert,
    clear_xero_tokens as _clear,
)


async def get_org_settings(org_id: str):
    return await _get(org_id)


async def upsert_org_settings(settings):
    return await _upsert(settings)


async def clear_xero_tokens(org_id: str) -> None:
    await _clear(org_id)
