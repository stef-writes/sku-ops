"""Product family lifecycle: create, update, delete parent product concepts.

A Product groups related SKUs. Deleting a product cascades to soft-delete
all child SKUs and their vendor items.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from catalog.domain.product_family import Product
from catalog.infrastructure.department_repo import department_repo
from catalog.infrastructure.product_family_repo import product_family_repo
from catalog.infrastructure.sku_repo import sku_repo
from catalog.infrastructure.vendor_item_repo import vendor_item_repo
from shared.infrastructure.database import get_org_id, transaction
from shared.infrastructure.domain_events import dispatch
from shared.kernel.domain_events import CatalogChanged
from shared.kernel.errors import ResourceNotFoundError

logger = logging.getLogger(__name__)


async def create_product(
    name: str,
    category_id: str,
    category_name: str = "",
    description: str = "",
) -> Product:
    """Create a product parent record."""
    org_id = get_org_id()
    dept = await department_repo.get_by_id(category_id)
    if not dept:
        raise ResourceNotFoundError("Department", category_id)

    product = Product(
        name=name,
        description=description,
        category_id=category_id,
        category_name=category_name or dept.name,
        organization_id=org_id,
    )

    async with transaction():
        await product_family_repo.insert(product)

    await dispatch(CatalogChanged(org_id=org_id, product_ids=(product.id,), change_type="created"))
    logger.info(
        "product.created",
        extra={"org_id": org_id, "product_id": product.id, "product_name": product.name},
    )
    return product


async def update_product(
    product_id: str,
    updates: dict,
) -> Product:
    """Update a product parent record."""
    product = await product_family_repo.get_by_id(product_id)
    if not product:
        raise ResourceNotFoundError("Product", product_id)

    if "category_id" in updates:
        dept = await department_repo.get_by_id(updates["category_id"])
        if dept:
            updates["category_name"] = dept.name

    updates["updated_at"] = datetime.now(UTC).isoformat()

    async with transaction():
        result = await product_family_repo.update(product_id, updates)
    if not result:
        raise ResourceNotFoundError("Product", product_id)

    org_id = get_org_id()
    await dispatch(CatalogChanged(org_id=org_id, product_ids=(product_id,), change_type="updated"))
    logger.info("product.updated", extra={"org_id": org_id, "product_id": product_id})
    return result


async def delete_product(product_id: str) -> None:
    """Soft-delete a product and cascade to all child SKUs and their vendor items."""
    product = await product_family_repo.get_by_id(product_id)
    if not product:
        raise ResourceNotFoundError("Product", product_id)

    child_skus = await sku_repo.find_by_product_id(product_id)

    deleted_ids = [s.id for s in child_skus] + [product_id]
    async with transaction():
        for s in child_skus:
            await vendor_item_repo.soft_delete_by_sku(s.id)
            await sku_repo.delete(s.id)
            await department_repo.increment_sku_count(s.category_id, -1)
        await product_family_repo.soft_delete(product_id)

    org_id = get_org_id()
    await dispatch(
        CatalogChanged(org_id=org_id, product_ids=tuple(deleted_ids), change_type="deleted")
    )
    logger.info(
        "product.deleted",
        extra={"org_id": org_id, "product_id": product_id, "cascade_sku_count": len(child_skus)},
    )
