"""
Google Generative AI (Gemini) client for receipt parsing, UOM classification, etc.
Uses google-generativeai SDK directly; no Emergent dependency.
"""
from typing import Optional
import os
import logging

logger = logging.getLogger(__name__)

GEMINI_MODEL = "gemini-1.5-flash"


def _get_model(system_instruction: Optional[str] = None):
    """Return configured GenerativeModel, or None if not configured."""
    api_key = os.environ.get("LLM_API_KEY")
    if not api_key:
        return None
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        try:
            if system_instruction:
                return genai.GenerativeModel(GEMINI_MODEL, system_instruction=system_instruction)
            return genai.GenerativeModel(GEMINI_MODEL)
        except TypeError:
            return genai.GenerativeModel(GEMINI_MODEL)
    except ImportError:
        logger.warning("google-generativeai not installed")
        return None


def generate_text(prompt: str, system_instruction: Optional[str] = None) -> Optional[str]:
    """Generate text from prompt. Returns response text or None on failure."""
    model = _get_model(system_instruction)
    if not model:
        return None
    try:
        response = model.generate_content(prompt)
        return response.text if response.text else None
    except Exception as e:
        logger.warning(f"Gemini generate_text failed: {e}")
        return None


def generate_with_image(
    prompt: str,
    image_bytes: bytes,
    mime_type: str = "image/jpeg",
    system_instruction: Optional[str] = None,
) -> Optional[str]:
    """Generate text from prompt + image. Returns response text or None."""
    model = _get_model(system_instruction)
    if not model:
        return None
    try:
        import io
        import PIL.Image
        img = PIL.Image.open(io.BytesIO(image_bytes))
        response = model.generate_content([prompt, img])
        return response.text if response.text else None
    except Exception as e:
        logger.warning(f"Gemini generate_with_image failed: {e}")
        return None


def generate_with_pdf(
    prompt: str,
    pdf_path: str,
    system_instruction: Optional[str] = None,
) -> Optional[str]:
    """Generate text from prompt + PDF file. Returns response text or None."""
    model = _get_model(system_instruction)
    if not model:
        return None
    try:
        import google.generativeai as genai
        pdf_file = genai.upload_file(path=pdf_path, mime_type="application/pdf")
        response = model.generate_content([prompt, pdf_file])
        return response.text if response.text else None
    except Exception as e:
        logger.warning(f"Gemini generate_with_pdf failed: {e}")
        return None
