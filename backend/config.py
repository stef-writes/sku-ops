"""
Central configuration - environment-aware settings.

Set ENV to control behavior:
  - development  Local dev; permissive defaults, demo creds allowed
  - staging      Preview/tenant deployments; stricter, JWT required, no demo creds unless set
  - production   Live; requires explicit secrets, strict CORS
  - test         Pytest in-process; stub adapters, in-memory DB (conftest sets this)

When ENV is unset, defaults to development.
"""
import os
from pathlib import Path

# Load .env early (before other modules read env)
_ROOT = Path(__file__).resolve().parent
if (_ROOT / ".env").exists():
    from dotenv import load_dotenv
    load_dotenv(_ROOT / ".env")

_ENV = os.environ.get("ENV", "development").lower().strip()


def _is(env: str) -> bool:
    """Check if current env matches."""
    return _ENV == env


# Environment flags
is_development = _is("development")
is_staging = _is("staging")
is_production = _is("production")
is_test = _is("test")

# Derived: any non-dev deployment
is_deployed = is_staging or is_production

# Database
DATABASE_URL = os.environ.get("DATABASE_URL") or (
    "sqlite:///:memory:" if is_test else "sqlite:///./data/sku_ops.db"
)

# Auth
def _resolve_jwt_secret() -> str:
    raw = os.environ.get("JWT_SECRET", "").strip()
    if is_production and (not raw or raw == "hardware-store-secret-key"):
        raise RuntimeError("JWT_SECRET must be set in production. Do not use default.")
    if is_staging and not raw:
        raise RuntimeError("JWT_SECRET must be set in staging.")
    return raw or "hardware-store-secret-key"

JWT_SECRET = _resolve_jwt_secret()
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24

# CORS
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*")
cors_is_permissive = CORS_ORIGINS == "*" or "*" in CORS_ORIGINS.split(",")
cors_warn_in_deployed = is_deployed and cors_is_permissive

# Payment
PAYMENT_ADAPTER = os.environ.get("PAYMENT_ADAPTER", "").lower().strip()
STRIPE_API_KEY = os.environ.get("STRIPE_API_KEY", "").strip()
# In test, always stub; in dev, stub if not configured; otherwise stripe when key set
def _payment_adapter() -> str:
    if is_test:
        return "stub"
    if PAYMENT_ADAPTER:
        return PAYMENT_ADAPTER
    return "stripe" if STRIPE_API_KEY else "stub"

payment_adapter = _payment_adapter()

# Demo / seed
def _demo_email() -> str:
    env_val = os.environ.get("DEMO_USER_EMAIL", "").strip()
    if env_val:
        return env_val
    return "admin@demo.local" if is_development else ""

def _demo_password() -> str:
    env_val = os.environ.get("DEMO_USER_PASSWORD", "").strip()
    if env_val:
        return env_val
    return "demo123" if is_development else ""

DEMO_USER_EMAIL = _demo_email()
DEMO_USER_PASSWORD = _demo_password()

# Seed on startup: always in dev/test; in staging/prod only if demo creds configured
seed_on_startup = is_development or is_test or bool(DEMO_USER_EMAIL)

# LLM - optional. Prefer Ollama (free, local, open-source) when configured; else Gemini (cloud).
# Ollama: install from ollama.com, run `ollama pull llama3.2` and `ollama pull llama3.2-vision`
# In development: auto-enable Ollama (try localhost:11434). Set OLLAMA_BASE_URL="" to disable.
_ollama_url = os.environ.get("OLLAMA_BASE_URL", "").strip().rstrip("/")
if is_development and not _ollama_url and "OLLAMA_BASE_URL" not in os.environ:
    _ollama_url = "http://localhost:11434"  # Auto-try Ollama in dev when uv/npm run dev
OLLAMA_BASE_URL = _ollama_url or "http://localhost:11434"
OLLAMA_ENABLED = bool(_ollama_url)
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2").strip() or "llama3.2"
OLLAMA_VISION_MODEL = os.environ.get("OLLAMA_VISION_MODEL", "llama3.2-vision").strip() or "llama3.2-vision"

# Gemini (Google) - cloud, free tier ~60 req/min, requires API key, data sent to Google
LLM_API_KEY = os.environ.get("LLM_API_KEY", "").strip()
GEMINI_AVAILABLE = bool(LLM_API_KEY)
LLM_SETUP_URL = "https://aistudio.google.com/app/apikey"

# Any LLM available. Prefer Ollama (free) when both configured.
LLM_AVAILABLE = OLLAMA_ENABLED or GEMINI_AVAILABLE

# E2E / live tests: backend URL to hit. Set REACT_APP_BACKEND_URL or E2E_BACKEND_URL.
def _e2e_backend_url() -> str:
    url = (
        os.environ.get("E2E_BACKEND_URL")
        or os.environ.get("REACT_APP_BACKEND_URL", "")
    ).rstrip("/")
    if url:
        return url
    if is_development:
        return "http://localhost:8000"
    return "https://hardware-pos-stripe.preview.emergentagent.com"

E2E_BACKEND_URL = _e2e_backend_url()
