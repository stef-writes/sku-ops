"""
LLM client: Ollama (free, local) or Google Gemini (cloud).
Prefer Ollama when OLLAMA_BASE_URL is set - no API key, data stays local.
"""
import base64
import io
import logging
from typing import Optional

import requests

from config import (
    GEMINI_AVAILABLE,
    LLM_API_KEY,
    OLLAMA_BASE_URL,
    OLLAMA_ENABLED,
    OLLAMA_MODEL,
    OLLAMA_VISION_MODEL,
)

logger = logging.getLogger(__name__)

GEMINI_MODEL = "gemini-1.5-flash"
OLLAMA_TIMEOUT = 120  # Vision models can be slow


# ---------------------------------------------------------------------------
# Ollama (free, local, open-source)
# ---------------------------------------------------------------------------


def _ollama_generate_text(prompt: str, system_instruction: Optional[str] = None) -> Optional[str]:
    """Generate text via Ollama. Returns None on failure."""
    if not OLLAMA_ENABLED:
        return None
    messages = []
    if system_instruction:
        messages.append({"role": "system", "content": system_instruction})
    messages.append({"role": "user", "content": prompt})
    try:
        r = requests.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json={"model": OLLAMA_MODEL, "messages": messages, "stream": False},
            timeout=OLLAMA_TIMEOUT,
        )
        r.raise_for_status()
        data = r.json()
        return (data.get("message") or {}).get("content")
    except requests.exceptions.ConnectionError:
        logger.debug("Ollama not reachable (not running?)")
        return None
    except Exception as e:
        logger.warning(f"Ollama generate_text failed: {e}")
        return None


def _ollama_generate_with_image(
    prompt: str,
    image_bytes: bytes,
    mime_type: str = "image/jpeg",
    system_instruction: Optional[str] = None,
) -> str:
    """Generate text from image via Ollama vision model. Raises ValueError on failure."""
    if not OLLAMA_ENABLED:
        raise ValueError("Ollama not configured. Set OLLAMA_BASE_URL or LLM_API_KEY.")
    b64 = base64.b64encode(image_bytes).decode("ascii")
    img_data = f"data:{mime_type};base64,{b64}"
    messages = []
    if system_instruction:
        messages.append({"role": "system", "content": system_instruction})
    messages.append({"role": "user", "content": prompt, "images": [img_data]})
    try:
        r = requests.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json={"model": OLLAMA_VISION_MODEL, "messages": messages, "stream": False},
            timeout=OLLAMA_TIMEOUT,
        )
        r.raise_for_status()
        data = r.json()
        content = (data.get("message") or {}).get("content")
        if not content or not str(content).strip():
            raise ValueError("Ollama returned no content")
        return str(content)
    except requests.exceptions.ConnectionError:
        raise ValueError(
            "Ollama not reachable. Is it running? Try: ollama serve"
        ) from None
    except requests.exceptions.HTTPError as e:
        if e.response and e.response.status_code == 404:
            raise ValueError(
                f"Vision model not found. Run: ollama pull {OLLAMA_VISION_MODEL}"
            ) from e
        raise ValueError(f"Ollama error: {e}") from e


def _ollama_generate_with_pdf(
    prompt: str,
    pdf_path: str,
    system_instruction: Optional[str] = None,
) -> str:
    """Render PDF first page to image, send to Ollama vision."""
    try:
        from pdf2image import convert_from_path

        images = convert_from_path(pdf_path, first_page=1, last_page=1, dpi=150)
        if not images:
            raise ValueError("Could not render PDF to image")
        buf = io.BytesIO()
        images[0].save(buf, format="PNG")
        return _ollama_generate_with_image(
            prompt, buf.getvalue(), "image/png", system_instruction
        )
    except ImportError:
        raise ValueError("PDF to image requires: pip install pdf2image, brew install poppler") from None


# ---------------------------------------------------------------------------
# Gemini (Google cloud)
# ---------------------------------------------------------------------------


def _get_gemini_model(system_instruction: Optional[str] = None):
    """Return configured GenerativeModel, or None if not configured."""
    if not GEMINI_AVAILABLE:
        return None
    try:
        import google.generativeai as genai

        genai.configure(api_key=LLM_API_KEY)
        try:
            if system_instruction:
                return genai.GenerativeModel(GEMINI_MODEL, system_instruction=system_instruction)
            return genai.GenerativeModel(GEMINI_MODEL)
        except TypeError:
            return genai.GenerativeModel(GEMINI_MODEL)
    except ImportError:
        logger.warning("google-generativeai not installed")
        return None


def _extract_gemini_text(response) -> str:
    """Extract text from Gemini response. Raises ValueError on blocked/empty."""
    if not response:
        raise ValueError("No response from model")
    text = getattr(response, "text", None)
    if text and str(text).strip():
        return str(text)
    prompt_feedback = getattr(response, "prompt_feedback", None)
    if prompt_feedback and getattr(prompt_feedback, "block_reason", None):
        raise ValueError(f"Content blocked: {prompt_feedback.block_reason}")
    candidates = getattr(response, "candidates", None) or []
    for c in candidates:
        parts = getattr(c, "content", None) and getattr(c.content, "parts", None) or []
        for p in parts:
            if hasattr(p, "text") and p.text:
                return p.text
    raise ValueError("Model returned no extractable text")


def _gemini_generate_text(prompt: str, system_instruction: Optional[str] = None) -> Optional[str]:
    model = _get_gemini_model(system_instruction)
    if not model:
        return None
    try:
        response = model.generate_content(prompt)
        return _extract_gemini_text(response)
    except Exception as e:
        logger.warning(f"Gemini generate_text failed: {e}")
        return None


def _gemini_generate_with_image(
    prompt: str,
    image_bytes: bytes,
    mime_type: str = "image/jpeg",
    system_instruction: Optional[str] = None,
) -> str:
    model = _get_gemini_model(system_instruction)
    if not model:
        raise ValueError("LLM not configured")
    import PIL.Image

    img = PIL.Image.open(io.BytesIO(image_bytes))
    response = model.generate_content([prompt, img])
    return _extract_gemini_text(response)


def _gemini_generate_with_pdf(
    prompt: str,
    pdf_path: str,
    system_instruction: Optional[str] = None,
) -> str:
    model = _get_gemini_model(system_instruction)
    if not model:
        raise ValueError("LLM not configured")
    import google.generativeai as genai

    pdf_file = genai.upload_file(path=pdf_path, mime_type="application/pdf")
    response = model.generate_content([prompt, pdf_file])
    return _extract_gemini_text(response)


# ---------------------------------------------------------------------------
# Unified API (prefer Ollama when available)
# ---------------------------------------------------------------------------


def generate_text(prompt: str, system_instruction: Optional[str] = None) -> Optional[str]:
    """Generate text. Prefer Ollama (free, local); fall back to Gemini."""
    result = _ollama_generate_text(prompt, system_instruction)
    if result:
        return result
    return _gemini_generate_text(prompt, system_instruction)


def generate_with_image(
    prompt: str,
    image_bytes: bytes,
    mime_type: str = "image/jpeg",
    system_instruction: Optional[str] = None,
) -> str:
    """Generate from image. Prefer Ollama; fall back to Gemini. Raises ValueError on failure."""
    if OLLAMA_ENABLED:
        try:
            return _ollama_generate_with_image(prompt, image_bytes, mime_type, system_instruction)
        except ValueError:
            pass  # Fall through to Gemini
    if GEMINI_AVAILABLE:
        try:
            return _gemini_generate_with_image(prompt, image_bytes, mime_type, system_instruction)
        except ValueError:
            raise
        except Exception as e:
            err = str(e).lower()
            if "quota" in err or "rate" in err or "429" in err:
                raise ValueError("Gemini rate limit. Try again in a minute or use Ollama (free).") from e
            if "invalid" in err and "key" in err:
                raise ValueError("Invalid LLM_API_KEY. Check .env") from e
            raise
    raise ValueError(
        "No LLM configured. Set OLLAMA_BASE_URL (free, local) or LLM_API_KEY (Gemini)."
    )


def generate_with_pdf(
    prompt: str,
    pdf_path: str,
    system_instruction: Optional[str] = None,
) -> str:
    """Generate from PDF. Prefer Ollama (renders to image); fall back to Gemini (native)."""
    if OLLAMA_ENABLED:
        try:
            return _ollama_generate_with_pdf(prompt, pdf_path, system_instruction)
        except ValueError:
            pass
    if GEMINI_AVAILABLE:
        try:
            return _gemini_generate_with_pdf(prompt, pdf_path, system_instruction)
        except Exception as e:
            err = str(e).lower()
            if "quota" in err or "rate" in err or "429" in err:
                raise ValueError("Gemini rate limit. Try Ollama (free, local) or retry later.") from e
            raise
    raise ValueError(
        "No LLM configured. Set OLLAMA_BASE_URL (free, local) or LLM_API_KEY (Gemini)."
    )
