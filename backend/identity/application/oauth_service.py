"""OAuth state management — application facade for identity-owned OAuth state.

Other contexts import from here rather than from identity.infrastructure directly.
"""

from identity.infrastructure.oauth_state_repo import (
    pop_oauth_state as _pop,
)
from identity.infrastructure.oauth_state_repo import (
    save_oauth_state as _save,
)


async def save_oauth_state(state: str) -> None:
    await _save(state)


async def pop_oauth_state(state: str) -> str | None:
    return await _pop(state)
