"""User repository port — testable contract for user persistence."""
from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class UserRepoPort(Protocol):

    async def get_by_id(self, user_id: str) -> Optional[dict]: ...

    async def get_by_email(self, email: str) -> Optional[dict]: ...

    async def insert(self, user_dict: dict) -> None: ...

    async def update(self, user_id: str, updates: dict) -> Optional[dict]: ...

    async def list_contractors(
        self, organization_id: Optional[str] = None,
    ) -> list: ...

    async def count_contractors(
        self, organization_id: Optional[str] = None,
    ) -> int: ...

    async def delete_contractor(self, contractor_id: str) -> int: ...
