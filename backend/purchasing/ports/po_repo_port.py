"""Port for purchase order persistence."""

from abc import ABC, abstractmethod

from purchasing.domain.purchase_order import (
    POItemRow,
    POItemStatus,
    PORow,
    PurchaseOrder,
    PurchaseOrderItem,
)


class PORepoPort(ABC):
    @abstractmethod
    async def insert_po(self, po: PurchaseOrder) -> None: ...

    @abstractmethod
    async def insert_items(self, items: list[PurchaseOrderItem]) -> None: ...

    @abstractmethod
    async def list_pos(self, status: str | None = None) -> list[PORow]: ...

    @abstractmethod
    async def get_po(self, po_id: str) -> PORow | None: ...

    @abstractmethod
    async def get_po_items(self, po_id: str) -> list[POItemRow]: ...

    @abstractmethod
    async def update_po_item(
        self,
        item_id: str,
        status: POItemStatus,
        product_id: str | None = None,
        delivered_qty: float | None = None,
    ) -> bool: ...

    @abstractmethod
    async def update_po_status(
        self,
        po_id: str,
        status: str,
        received_at: str | None = None,
        received_by_id: str | None = None,
        received_by_name: str | None = None,
    ) -> None: ...
