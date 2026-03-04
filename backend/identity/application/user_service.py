"""User application service — safe for cross-context import."""
from identity.infrastructure.user_repo import user_repo as _repo


async def get_user_by_id(user_id: str):
    return await _repo.get_by_id(user_id)


async def get_user_by_email(email: str):
    return await _repo.get_by_email(email)


async def list_contractors(org_id: str):
    return await _repo.list_contractors(org_id)


async def count_contractors(org_id: str) -> int:
    return await _repo.count_contractors(org_id)


async def insert_user(user_dict: dict):
    return await _repo.insert(user_dict)


async def update_user(user_id: str, data: dict):
    return await _repo.update(user_id, data)


async def delete_contractor(user_id: str):
    return await _repo.delete_contractor(user_id)
