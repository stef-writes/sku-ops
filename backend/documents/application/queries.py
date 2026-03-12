"""Document application queries — safe for cross-context import.

API and other bounded contexts import from here, never from documents.infrastructure directly.
Thin delegation layer that decouples consumers from infrastructure details.
"""

from documents.domain.document import Document
from documents.infrastructure.document_repo import document_repo as _doc_repo


async def list_documents(
    status: str | None = None,
    vendor_name: str | None = None,
    po_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Document]:
    return await _doc_repo.list_documents(
        status=status,
        vendor_name=vendor_name,
        po_id=po_id,
        limit=limit,
        offset=offset,
    )


async def get_document_by_id(doc_id: str) -> Document | None:
    return await _doc_repo.get_by_id(doc_id)
