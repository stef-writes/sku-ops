FROM python:3.13-slim-bookworm AS builder

WORKDIR /build

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install uv

# Copy workspace root + backend member for uv workspace resolution
COPY pyproject.toml ./pyproject.toml
COPY uv.lock ./
COPY backend/pyproject.toml ./backend/pyproject.toml
RUN uv sync --frozen --no-dev --no-editable --package sku-ops-backend


FROM python:3.13-slim-bookworm AS runtime

WORKDIR /app

# Runtime-only native deps (no build headers)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libpq5 \
        tesseract-ocr \
        poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Non-root user
RUN groupadd --gid 1001 appgroup && \
    useradd --uid 1001 --gid 1001 --no-create-home --shell /sbin/nologin appuser

# Copy installed packages and uv from builder
COPY --from=builder /build/.venv /app/.venv
COPY --from=builder /usr/local/bin/uv /usr/local/bin/uv

# Copy application source only — devtools is intentionally excluded
COPY backend/ .

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TIKTOKEN_CACHE_DIR="/app/.tiktoken"

# Pre-download tiktoken encoding data to avoid runtime network calls
RUN python -c "import tiktoken; tiktoken.get_encoding('cl100k_base')"

RUN chown -R appuser:appgroup /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://localhost:' + os.environ.get('PORT','8000') + '/api/health')" || exit 1

CMD ["sh", "-c", "python -m uvicorn server:app --host 0.0.0.0 --port ${PORT:-8000} --workers ${WORKERS:-1}"]
