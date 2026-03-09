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


# Project root = backend/ (walk up from this file to find it)
def _find_backend_root() -> Path:
    """Locate the backend root by finding the directory containing server.py."""
    d = Path(__file__).resolve().parent
    for _ in range(10):
        if (d / "server.py").exists():
            return d
        d = d.parent
    return Path.cwd()

PROJECT_ROOT = _find_backend_root()

# Resolve the runtime environment from the real process environment first.
# Deployed environments must inject vars explicitly rather than inheriting
# a stray local backend/.env file from the filesystem.
_requested_env = os.environ.get("ENV", "").lower().strip()
_ENV = _requested_env or "development"

# Load backend/.env only for local-style runs. This keeps developer ergonomics
# for dev/test while making staging/production rely strictly on injected vars.
_env_file = PROJECT_ROOT / ".env"
if _ENV in {"development", "test"} and _env_file.exists():
    from dotenv import load_dotenv
    load_dotenv(_env_file)


def _is(env: str) -> bool:
    """Check if current env matches."""
    return env == _ENV


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

if is_deployed and not DATABASE_URL.startswith(("postgresql://", "postgres://")):
    raise RuntimeError(
        "DATABASE_URL must be a PostgreSQL connection string in staging/production. "
        "Got a non-PostgreSQL URL. Set DATABASE_URL=postgresql://user:pass@host:5432/db"
    )

# Redis — required for multi-worker (WORKERS > 1); optional in dev/test
REDIS_URL = os.environ.get("REDIS_URL", "").strip()

# Auth
_DEV_JWT_FALLBACK = "hardware-store-" + "secret-key"

def _resolve_jwt_secret() -> str:
    raw = os.environ.get("JWT_SECRET", "").strip()
    if is_production and (not raw or raw == _DEV_JWT_FALLBACK):
        raise RuntimeError("JWT_SECRET must be set in production. Do not use default.")
    if is_staging and (not raw or raw == _DEV_JWT_FALLBACK):
        raise RuntimeError(
            "JWT_SECRET must be set in staging and must not be the default. "
            'Generate one with: python -c "import secrets; print(secrets.token_hex(32))"'
        )
    return raw or _DEV_JWT_FALLBACK

JWT_SECRET = _resolve_jwt_secret()
JWT_ALGORITHM = "HS256"
JWT_ACCESS_EXPIRATION_MINUTES = int(os.environ.get("JWT_ACCESS_EXPIRATION_MINUTES", "15"))
REFRESH_TOKEN_EXPIRATION_DAYS = int(os.environ.get("REFRESH_TOKEN_EXPIRATION_DAYS", "30"))

# CORS — strict enforcement in deployed environments
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*")
cors_is_permissive = CORS_ORIGINS == "*" or "*" in CORS_ORIGINS.split(",")
cors_warn_in_deployed = is_deployed and cors_is_permissive

def _enforce_cors() -> None:
    if is_production and cors_is_permissive:
        raise RuntimeError(
            "CORS_ORIGINS must not be '*' in production. "
            "Set CORS_ORIGINS=https://your-domain.com"
        )
    if is_staging and cors_is_permissive:
        raise RuntimeError(
            "CORS_ORIGINS must not be '*' in staging. "
            "Set CORS_ORIGINS to your staging domain(s)."
        )

_enforce_cors()

# Sentry (optional — set SENTRY_DSN to enable)
SENTRY_DSN = os.environ.get("SENTRY_DSN", "").strip()

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

# Seed on startup: dev/test only. Never in production, even if demo creds are set.
seed_on_startup = (is_development or is_test) and bool(DEMO_USER_EMAIL)

# Reset/seed endpoints: dev/test only. Cannot be enabled in production or staging.
ALLOW_RESET = is_development or is_test

# AI - Anthropic Claude. Set ANTHROPIC_API_KEY to enable.
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
ANTHROPIC_AVAILABLE = bool(ANTHROPIC_API_KEY)
# Keep bare model names for non-agent services (OCR, UOM classification, enrichment)
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6").strip() or "claude-sonnet-4-6"
ANTHROPIC_FAST_MODEL = os.environ.get("ANTHROPIC_FAST_MODEL", "claude-haiku-4-5").strip() or "claude-haiku-4-5"

# OpenAI — used for product semantic search embeddings (text-embedding-3-small)
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
OPENAI_AVAILABLE = bool(OPENAI_API_KEY)

# OpenRouter — unified model gateway for all agent LLM calls
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()
OPENROUTER_BASE_URL = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").strip()
OPENROUTER_AVAILABLE = bool(OPENROUTER_API_KEY)

# ── Agent model — single source of truth ─────────────────────────────────────
# Priority: env AGENT_PRIMARY_MODEL > models.yaml > built-in default
def _load_agent_model() -> str:
    env_override = os.environ.get("AGENT_PRIMARY_MODEL", "").strip()
    if env_override:
        return env_override
    try:
        import yaml
        _yaml_path = PROJECT_ROOT / "models.yaml"
        if _yaml_path.exists():
            data = yaml.safe_load(_yaml_path.read_text()) or {}
            model = (data.get("primary") or "").strip()
            if model:
                return model
    except (OSError, ValueError, KeyError):
        pass
    return "anthropic:claude-sonnet-4-6"

AGENT_PRIMARY_MODEL: str = _load_agent_model()
LLM_SETUP_URL = "https://console.anthropic.com/"
LLM_AVAILABLE = ANTHROPIC_AVAILABLE  # alias used by enrichment/uom services
# Per-session AI spend cap in USD. 0 = unlimited. Set SESSION_COST_CAP=2.00 in .env.
SESSION_COST_CAP = float(os.environ.get("SESSION_COST_CAP", "2.00"))

# Frontend URL — used for OAuth callbacks and cross-origin redirects in split deploys.
# In same-origin setups this can be left empty (redirects stay relative).
FRONTEND_URL = os.environ.get("FRONTEND_URL", "").strip().rstrip("/")

# Xero OAuth 2.0 — register a Xero app at developer.xero.com to get these.
# XERO_REDIRECT_URI must match the callback URL registered in your Xero app.
XERO_CLIENT_ID = os.environ.get("XERO_CLIENT_ID", "").strip()
XERO_CLIENT_SECRET = os.environ.get("XERO_CLIENT_SECRET", "").strip()
XERO_REDIRECT_URI = os.environ.get("XERO_REDIRECT_URI", "").strip()
# Hour of day (UTC, 0-23) when the nightly Xero sync job fires. Default: 2 AM UTC.
XERO_SYNC_HOUR = int(os.environ.get("XERO_SYNC_HOUR", "2"))
