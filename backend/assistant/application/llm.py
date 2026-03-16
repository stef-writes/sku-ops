"""LLM client for non-agent uses (OCR, UOM classification, enrichment).

Uses the LLM infrastructure adapter when available, falls back to direct
Anthropic SDK construction for backward compatibility.
"""

import base64
import logging

from assistant.infrastructure.llm import get_provider
from shared.infrastructure.config import (
    ANTHROPIC_API_KEY,
    ANTHROPIC_AVAILABLE,
    ANTHROPIC_FAST_MODEL,
    ANTHROPIC_MODEL,
)

logger = logging.getLogger(__name__)


def _get_client():
    """Return configured Anthropic client, preferring the infrastructure adapter."""
    try:
        provider = get_provider()
        client = provider.get_raw_client()
        if client is not None:
            return client
    except RuntimeError:
        pass

    if not ANTHROPIC_AVAILABLE:
        return None
    try:
        import anthropic

        return anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    except ImportError:
        logger.warning("anthropic package not installed. Run: pip install anthropic")
        return None


def _detect_media_type(image_bytes: bytes) -> str:
    """Detect image media type from bytes header."""
    if image_bytes[:4] == b"\x89PNG":
        return "image/png"
    if image_bytes[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if image_bytes[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


def generate_text(
    prompt: str,
    system_instruction: str | None = None,
    model_id: str | None = None,
) -> str | None:
    """Generate text. Returns None if LLM is not configured.

    When model_id is provided, uses the active LLM provider (OpenRouter or Anthropic).
    When model_id is None, uses ANTHROPIC_FAST_MODEL via raw client (legacy path).
    """
    if model_id:
        try:
            provider = get_provider()
            return provider.generate_text(prompt, system_instruction, model_id)
        except RuntimeError:
            pass
    client = _get_client()
    if not client:
        return None
    try:
        kwargs = {
            "model": ANTHROPIC_FAST_MODEL,
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system_instruction:
            kwargs["system"] = system_instruction
        response = client.messages.create(**kwargs)
        return response.content[0].text
    except Exception as e:
        logger.warning("Anthropic generate_text failed: %s", e)
        return None


def generate_with_image(
    prompt: str,
    image_bytes: bytes,
    system_instruction: str | None = None,
) -> str:
    """Generate from image. Raises ValueError on failure or if not configured."""
    client = _get_client()
    if not client:
        raise ValueError("LLM not configured. Set ANTHROPIC_API_KEY in backend/.env")
    media_type = _detect_media_type(image_bytes)
    image_data = base64.standard_b64encode(image_bytes).decode("utf-8")
    try:
        kwargs = {
            "model": ANTHROPIC_MODEL,
            "max_tokens": 4096,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_data,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        }
        if system_instruction:
            kwargs["system"] = system_instruction
        response = client.messages.create(**kwargs)
        return response.content[0].text
    except Exception as e:
        err = str(e).lower()
        if "rate" in err or "429" in err or "overloaded" in err:
            raise ValueError("Anthropic rate limit hit. Try again in a minute.") from e
        if "authentication" in err or "api_key" in err:
            raise ValueError("Invalid ANTHROPIC_API_KEY. Check backend/.env") from e
        if "model" in err or "invalid_request" in err or "not_found" in err or "400" in err:
            raise ValueError(
                f"Anthropic model error (model={ANTHROPIC_MODEL}): {e}. "
                "Check ANTHROPIC_MODEL in your environment."
            ) from e
        raise ValueError(f"Anthropic API error: {e}") from e


def generate_with_pdf(
    prompt: str,
    pdf_path: str,
    system_instruction: str | None = None,
) -> str:
    """Generate from PDF via Anthropic native PDF support. Raises ValueError on failure."""
    client = _get_client()
    if not client:
        raise ValueError("LLM not configured. Set ANTHROPIC_API_KEY in backend/.env")
    with open(pdf_path, "rb") as f:
        pdf_data = base64.standard_b64encode(f.read()).decode("utf-8")
    try:
        kwargs = {
            "model": ANTHROPIC_MODEL,
            "max_tokens": 4096,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "document",
                            "source": {
                                "type": "base64",
                                "media_type": "application/pdf",
                                "data": pdf_data,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
            "betas": ["pdfs-2024-09-25"],
        }
        if system_instruction:
            kwargs["system"] = system_instruction
        response = client.beta.messages.create(**kwargs)
        return response.content[0].text
    except Exception as e:
        err = str(e).lower()
        if "rate" in err or "429" in err or "overloaded" in err:
            raise ValueError("Anthropic rate limit hit. Try again in a minute.") from e
        if "authentication" in err or "api_key" in err:
            raise ValueError("Invalid ANTHROPIC_API_KEY. Check backend/.env") from e
        if "model" in err or "invalid_request" in err or "not_found" in err or "400" in err:
            raise ValueError(
                f"Anthropic model error (model={ANTHROPIC_MODEL}): {e}. "
                "Check ANTHROPIC_MODEL in your environment."
            ) from e
        raise ValueError(f"Anthropic API error: {e}") from e
