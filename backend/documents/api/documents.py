"""Document parse/import routes."""

import logging
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile

from documents.application.import_service import import_document_wired
from documents.application.parse_service import parse_document_with_ai
from documents.application.queries import get_document_by_id
from documents.application.queries import list_documents as query_list_documents
from documents.domain.document import DocumentImportRequest
from shared.api.deps import AdminDep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/parse")
async def parse_document(
    file: Annotated[UploadFile, File(...)],
    current_user: AdminDep,
    use_ai: bool = False,
):
    """Parse image or PDF. use_ai=true uses Claude (requires ANTHROPIC_API_KEY); default uses free OCR."""
    contents = await file.read()
    content_type = (file.content_type or "").lower()
    filename = file.filename or ""

    if not use_ai:
        raise HTTPException(
            status_code=501,
            detail="OCR parsing is not available. Use use_ai=true with an Anthropic API key.",
        )

    try:
        return await parse_document_with_ai(contents, content_type, filename, current_user)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except ValueError as e:
        detail = str(e)
        if "no content" in detail.lower():
            raise HTTPException(status_code=500, detail=detail) from e
        raise HTTPException(status_code=400, detail=detail) from e
    except Exception as e:
        logger.exception("Document parse error")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("")
async def list_documents(
    current_user: AdminDep,
    status: str | None = None,
    vendor_name: str | None = None,
    po_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
):
    """List uploaded/parsed documents."""
    return await query_list_documents(
        status=status,
        vendor_name=vendor_name,
        po_id=po_id,
        limit=limit,
        offset=offset,
    )


@router.get("/{doc_id}")
async def get_document(doc_id: str, current_user: AdminDep):
    doc = await get_document_by_id(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.post("/import")
async def import_document(
    data: DocumentImportRequest,
    current_user: AdminDep,
):
    """Import parsed products; create or match vendor."""
    try:
        return await import_document_wired(
            vendor_name=data.vendor_name,
            products=data.products,
            category_id=data.category_id,
            create_vendor_if_missing=data.create_vendor_if_missing,
            current_user=current_user,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
