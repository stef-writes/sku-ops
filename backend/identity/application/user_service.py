"""User application service — safe for cross-context import."""

from identity.domain.user import AdminUserCreate, User, UserCreate, UserUpdate  # noqa: F401
from identity.infrastructure.user_repo import user_repo as _repo


async def get_user_by_id(user_id: str):
    return await _repo.get_by_id(user_id)


async def get_users_by_ids(user_ids: list[str]) -> dict[str, User]:
    return await _repo.get_by_ids(user_ids)


async def get_user_by_email(email: str):
    return await _repo.get_by_email(email)


async def list_contractors(search: str | None = None):
    return await _repo.list_contractors(search=search)


async def count_contractors() -> int:
    return await _repo.count_contractors()


async def insert_user(user_dict: dict):
    return await _repo.insert(user_dict)


async def update_user(user_id: str, data: dict):
    return await _repo.update(user_id, data)


async def delete_contractor(user_id: str):
    return await _repo.delete_contractor(user_id)
