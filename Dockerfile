# syntax=docker/dockerfile:1
# Production image: the React bundle served by the FastAPI process, one origin.
# Build: docker build -t aimix .   Run: see docs/deployment.md
#
# Base images are pinned by digest, the tag kept for readers; Dependabot
# (.github/dependabot.yml) proposes new digests and versions.

# --- 1. Frontend bundle ------------------------------------------------------
# Node 24, as in CI (.github/workflows/ci.yml).
FROM node:24-alpine@sha256:06d7adf3e0ef61a13f1d28682726366f97a15aa1888c934d3ecec86c33918b53 AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- 2. Python dependencies --------------------------------------------------
# Python 3.12, as in .python-version (which CI uses too).
FROM python:3.12-slim-trixie@sha256:a0f57064cbdcd6285fa45f51237ab0b35ea8ebaed06a1f5973e89e19dfb86704 AS python-base

# uv installs the locked dependencies here; the runtime copies the virtualenv
# and leaves uv behind.
FROM python-base AS python-deps
COPY --from=ghcr.io/astral-sh/uv:0.11.28@sha256:0f36cb9361a3346885ca3677e3767016687b5a170c1a6b88465ec14aefec90aa /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project

# --- 3. Backend runtime ------------------------------------------------------
FROM python-base AS runtime
# DejaVu Sans is embedded in the PDFs agents save, so non-Latin text prints
# (PDF_FONT_PATH). Tesseract reads scanned PDFs and images (OCR); English and
# French match the DOCUMENT_OCR_LANGUAGES default, add a tesseract-ocr-<lang>
# package for more. One layer, so the apt lists never stay in the image.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        fonts-dejavu-core tesseract-ocr tesseract-ocr-eng tesseract-ocr-fra \
    && rm -rf /var/lib/apt/lists/*
# One thread per tesseract run: more made no page faster, and under a one-CPU
# quota they made each page about 3.5 times slower.
ENV OMP_THREAD_LIMIT=1

ENV PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

# The app runs as `aimix` (uid 10001). There is no USER line: the entrypoint
# starts as root only to hand the volume at AIMIX_DATA_DIR to `aimix`, then
# runs the command as `aimix` (or as it is, when started as another user).
ENV AIMIX_DATA_DIR=/data
RUN groupadd --gid 10001 aimix \
    && useradd --uid 10001 --gid aimix --create-home aimix \
    && mkdir "$AIMIX_DATA_DIR" \
    && chown aimix:aimix "$AIMIX_DATA_DIR"
COPY --chmod=0755 docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
ENTRYPOINT ["docker-entrypoint.sh"]

# Owned by root, so the app user can read the code and its dependencies but
# not change them.
WORKDIR /app
COPY --from=python-deps /app/.venv /app/.venv
COPY backend/ backend/
COPY --from=frontend /app/frontend/dist frontend/dist

# Production by default: the settings refuse to start without SECRET_KEY and
# ALLOWED_HOSTS. SQLite and the users' files live on the volume.
ENV APP_ENV=production \
    FRONTEND_DIST_DIR=/app/frontend/dist \
    DATABASE_URL=sqlite:///${AIMIX_DATA_DIR}/aimix.sqlite3 \
    AGENT_WORKSPACE_DIR=${AIMIX_DATA_DIR}/workspace

# Set for Railway's edge, which hands the app [client, edge hop] in
# X-Forwarded-For. Without a proxy in front, run with TRUSTED_PROXY_HOPS=0; see
# docs/deployment.md, "Client address behind a proxy".
ENV TRUSTED_PROXY_HOPS=2 \
    FORWARDED_ALLOW_IPS="*"

WORKDIR /app/backend
EXPOSE 8000

# Docker's own probe (Railway uses healthcheckPath in railway.json instead). It
# sends the first ALLOWED_HOSTS entry as Host, since the app refuses others.
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 CMD ["python", "-c", "import os, urllib.request as r; host = os.environ.get('ALLOWED_HOSTS', 'localhost').split(',')[0].strip(); port = os.environ.get('PORT', '8000'); r.urlopen(r.Request('http://127.0.0.1:' + port + '/api/health', headers={'Host': host}), timeout=4)"]

# Migrate, then serve on the platform's $PORT. With TRUSTED_PROXY_HOPS above 0
# Uvicorn reads the proxy headers (FORWARDED_ALLOW_IPS), which is how it knows a
# request came over https. It also sets the client address to the leftmost
# X-Forwarded-For entry, which the client writes, so nothing relies on that
# address: the rate limits count TRUSTED_PROXY_HOPS entries from the right of
# the header instead. At 0 Uvicorn ignores the proxy headers.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn api.main:create_app --factory --host 0.0.0.0 --port ${PORT:-8000} $([ \"${TRUSTED_PROXY_HOPS:-0}\" -gt 0 ] && echo --proxy-headers || echo --no-proxy-headers)"]
