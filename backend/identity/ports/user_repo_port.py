"""User repository port — testable contract for user persistence."""
from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class UserRepoPort(Protocol):

    async def get_by_id(self, user_id: str) -> dict | None: ...

    async def get_by_email(self, email: str) -> dict | None: ...

    async def insert(self, user_dict: dict) -> None: ...

    async def update(self, user_id: str, updates: dict) -> dict | None: ...

    async def list_contractors(
        self, organization_id: str | None = None, search: str | None = None,
    ) -> list: ...

    async def count_contractors(
        self, organization_id: str | None = None,
    ) -> int: ...

    async def delete_contractor(self, contractor_id: str) -> int: ...
