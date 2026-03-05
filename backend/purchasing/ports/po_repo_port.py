"""Port for purchase order persistence."""
from abc import ABC, abstractmethod
from typing import List, Optional

from purchasing.domain.purchase_order import PurchaseOrder, PurchaseOrderItem, POItemStatus


class PORepoPort(ABC):

    @abstractmethod
    async def insert_po(self, po: PurchaseOrder) -> None: ...

    @abstractmethod
    async def insert_items(self, items: List[PurchaseOrderItem]) -> None: ...

    @abstractmethod
    async def list_pos(self, org_id: str, status: Optional[str] = None) -> List[dict]: ...

    @abstractmethod
    async def get_po(self, po_id: str, org_id: str) -> Optional[dict]: ...

    @abstractmethod
    async def get_po_items(self, po_id: str) -> List[dict]: ...

    @abstractmethod
    async def update_po_item(
        self,
        item_id: str,
        status: POItemStatus,
        product_id: Optional[str] = None,
        delivered_qty: Optional[float] = None,
    ) -> None: ...

    @abstractmethod
    async def update_po_status(
        self,
        po_id: str,
        status: str,
        received_at: Optional[str] = None,
        received_by_id: Optional[str] = None,
        received_by_name: Optional[str] = None,
    ) -> None: ...
