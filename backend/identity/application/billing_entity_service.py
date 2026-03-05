"""Billing entity application service — safe for cross-context import.

Other bounded contexts import from here, never from identity.infrastructure directly.
"""
from identity.infrastructure.billing_entity_repo import billing_entity_repo


async def ensure_billing_entity(name: str, organization_id: str, conn=None) -> dict:
    """Get existing billing entity by name, or auto-create a minimal one."""
    return await billing_entity_repo.ensure_billing_entity(name, organization_id, conn=conn)
