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

# Reset endpoint: dev/test/demo only. Set ALLOW_RESET=true to enable in staging/prod.
ALLOW_RESET = is_development or is_test or os.environ.get("ALLOW_RESET", "").lower() == "true"

# AI - Anthropic Claude. Set ANTHROPIC_API_KEY to enable.
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
ANTHROPIC_AVAILABLE = bool(ANTHROPIC_API_KEY)
# Keep bare model names for non-agent services (OCR, UOM classification, enrichment)
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6").strip() or "claude-sonnet-4-6"
ANTHROPIC_FAST_MODEL = os.environ.get("ANTHROPIC_FAST_MODEL", "claude-haiku-4-5").strip() or "claude-haiku-4-5"

# OpenAI — used for product semantic search embeddings (text-embedding-3-small)
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
OPENAI_AVAILABLE = bool(OPENAI_API_KEY)

# ── Agent model — single source of truth ─────────────────────────────────────
# Priority: env AGENT_PRIMARY_MODEL > models.yaml > built-in default
def _load_agent_model() -> str:
    env_override = os.environ.get("AGENT_PRIMARY_MODEL", "").strip()
    if env_override:
        return env_override
    try:
        import yaml
        _yaml_path = _ROOT / "models.yaml"
        if _yaml_path.exists():
            data = yaml.safe_load(_yaml_path.read_text()) or {}
            model = (data.get("primary") or "").strip()
            if model:
                return model
    except Exception:
        pass
    return "anthropic:claude-sonnet-4-6"

AGENT_PRIMARY_MODEL: str = _load_agent_model()
LLM_SETUP_URL = "https://console.anthropic.com/"
LLM_AVAILABLE = ANTHROPIC_AVAILABLE  # alias used by enrichment/uom services
# Extended thinking for chat agents. 0 = off (uses Haiku). >0 = budget in tokens (switches to Sonnet).
# Reasonable range: 5000–16000. Set in .env as AGENT_THINKING_BUDGET=8000.
AGENT_THINKING_BUDGET = int(os.environ.get("AGENT_THINKING_BUDGET", "0"))
# Default thinking budget when mode=deep and AGENT_THINKING_BUDGET not set
DEFAULT_DEEP_THINKING_BUDGET = 8000
# Per-session AI spend cap in USD. 0 = unlimited. Set SESSION_COST_CAP=2.00 in .env.
SESSION_COST_CAP = float(os.environ.get("SESSION_COST_CAP", "2.00"))

# Xero OAuth 2.0 — register a Xero app at developer.xero.com to get these.
# XERO_REDIRECT_URI must match the callback URL registered in your Xero app.
XERO_CLIENT_ID = os.environ.get("XERO_CLIENT_ID", "").strip()
XERO_CLIENT_SECRET = os.environ.get("XERO_CLIENT_SECRET", "").strip()
XERO_REDIRECT_URI = os.environ.get("XERO_REDIRECT_URI", "").strip()

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
    return "http://localhost:8000"  # require E2E_BACKEND_URL or REACT_APP_BACKEND_URL when deployed

E2E_BACKEND_URL = _e2e_backend_url()
