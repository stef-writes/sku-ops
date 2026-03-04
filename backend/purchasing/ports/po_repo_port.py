"""Purchase order repository port — testable contract for PO persistence."""
from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class PORepoPort(Protocol):

    async def create_po(self, po: dict) -> None: ...

    async def create_po_items(self, items: list) -> None: ...

    async def list_pos(self, org_id: str, status: Optional[str] = None) -> list: ...

    async def get_po(self, po_id: str, org_id: str) -> Optional[dict]: ...

    async def get_po_items(self, po_id: str) -> list: ...

    async def update_po_item(
        self, item_id: str, status: str,
        product_id: Optional[str] = None,
        delivered_qty: Optional[int] = None,
    ) -> None: ...

    async def update_po_status(
        self, po_id: str, status: str,
        received_at: Optional[str] = None,
        received_by_id: Optional[str] = None,
        received_by_name: Optional[str] = None,
    ) -> None: ...
