"""Document parse service: AI-powered document parsing and persistence."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from assistant.application.llm import generate_with_image, generate_with_pdf
from documents.domain.document import Document
from documents.infrastructure.document_repo import document_repo
from shared.infrastructure.config import ANTHROPIC_AVAILABLE, LLM_SETUP_URL
from shared.infrastructure.db import get_org_id

if TYPE_CHECKING:
    from shared.kernel.types import CurrentUser

logger = logging.getLogger(__name__)

_PARSE_MAX_RETRIES = 2
_PARSE_RETRY_DELAYS = (5, 15)

_PROMPT_DIR = Path(__file__).resolve().parent.parent / "api"
_DOCUMENT_PARSE_SYSTEM: str | None = None


def _get_parse_system_prompt() -> str:
    global _DOCUMENT_PARSE_SYSTEM
    if _DOCUMENT_PARSE_SYSTEM is None:
        _DOCUMENT_PARSE_SYSTEM = (_PROMPT_DIR / "document_parse_prompt.md").read_text(
            encoding="utf-8"
        )
    return _DOCUMENT_PARSE_SYSTEM


async def persist_parsed_document(
    extracted: dict,
    filename: str,
    content_type: str,
    file_size: int,
    current_user: CurrentUser,
) -> dict:
    """Save parsed document to the archive and return the extracted data with document_id."""
    doc = Document(
        filename=filename,
        document_type="other",
        vendor_name=extracted.get("vendor_name"),
        file_hash=hashlib.sha256(filename.encode()).hexdigest()[:16],
        file_size=file_size,
        mime_type=content_type,
        parsed_data=json.dumps(extracted),
        status="parsed",
        uploaded_by_id=current_user.id,
        organization_id=get_org_id(),
    )
    await document_repo.insert(doc)
    extracted["document_id"] = doc.id
    return extracted


async def parse_document_with_ai(
    contents: bytes,
    content_type: str,
    filename: str,
    current_user: CurrentUser,
) -> dict:
    """Parse a document (image or PDF) using Claude AI.

    Returns the extracted structured data with a document_id after persisting.
    Raises ValueError on rate limit exhaustion or parse failure.
    Raises RuntimeError if AI is not configured.
    """
    if not ANTHROPIC_AVAILABLE:
        raise RuntimeError(
            f"AI not configured. Add ANTHROPIC_API_KEY to backend/.env — get a key at {LLM_SETUP_URL}"
        )

    system_prompt = _get_parse_system_prompt()
    is_pdf = content_type == "application/pdf" or filename.lower().endswith(".pdf")

    def _do_parse():
        if is_pdf:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tf:
                tf.write(contents)
                temp_path = tf.name
            try:
                return generate_with_pdf(
                    "Extract all product and vendor information. Return only valid JSON.",
                    temp_path,
                    system_instruction=system_prompt,
                )
            finally:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
        else:
            return generate_with_image(
                "Extract all product and vendor information. Return only valid JSON.",
                contents,
                system_instruction=system_prompt,
            )

    response = None
    for attempt in range(_PARSE_MAX_RETRIES + 1):
        try:
            response = await asyncio.to_thread(_do_parse)
            break
        except ValueError as e:
            err_lower = str(e).lower()
            if (
                "rate limit" in err_lower or "overloaded" in err_lower
            ) and attempt < _PARSE_MAX_RETRIES:
                delay = _PARSE_RETRY_DELAYS[attempt]
                logger.info("Rate limit, retrying in %ss (attempt %d)", delay, attempt + 1)
                await asyncio.sleep(delay)
            else:
                raise

    if not response or not str(response).strip():
        raise ValueError("Claude returned no content. The document may be unreadable or blocked.")

    json_match = re.search(r"\{[\s\S]*\}", response)
    try:
        extracted = json.loads(json_match.group()) if json_match else json.loads(response)
    except (json.JSONDecodeError, AttributeError) as e:
        logger.warning(
            "Failed to parse Claude response as JSON: %s\nResponse preview: %.200s", e, response
        )
        raise ValueError(
            "Could not extract structured data from the document. "
            "The file may be too complex, low quality, or not a recognized vendor invoice format."
        ) from e

    for p in extracted.get("products", []):
        qty = p.get("quantity", 1)
        p.setdefault("ordered_qty", qty)
        p.setdefault("delivered_qty", qty)
        if p["ordered_qty"] is None:
            p["ordered_qty"] = qty
        if p["delivered_qty"] is None:
            p["delivered_qty"] = qty
        p["_ai_parsed"] = True

    return await persist_parsed_document(
        extracted, filename, content_type, len(contents), current_user
    )
