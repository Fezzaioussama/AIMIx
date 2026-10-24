# syntax=docker/dockerfile:1
# Production image: the React bundle served by the FastAPI process, one origin.
# Build: docker build -t aimix .   Run: see docs/deployment.md

# --- 1. Frontend bundle ------------------------------------------------------
# Node 24, as in CI (.github/workflows/ci.yml).
FROM node:24-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- 2. Backend runtime ------------------------------------------------------
# Python 3.10, as in .python-version.
FROM python:3.10-slim AS runtime
COPY --from=ghcr.io/astral-sh/uv:0.11.28 /uv /usr/local/bin/uv
# DejaVu Sans, embedded in the PDFs agents save so non-Latin text prints (PDF_FONT_PATH).
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app
# Dependencies first, so a code change does not reinstall them.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend/ backend/
COPY --from=frontend /app/frontend/dist frontend/dist

# Production by default: the settings refuse to start without SECRET_KEY and
# ALLOWED_HOSTS. SQLite and the users' files live in /data, where the platform
# mounts a volume.
ENV APP_ENV=production \
    FRONTEND_DIST_DIR=/app/frontend/dist \
    DATABASE_URL=sqlite:////data/aimix.sqlite3 \
    AGENT_WORKSPACE_DIR=/data/workspace

RUN useradd --create-home --uid 10001 aimix && mkdir /data && chown aimix /data
USER aimix
WORKDIR /app/backend
EXPOSE 8000

# Migrate, then serve on the platform's $PORT. Proxy headers are trusted
# because the app is only reachable through the platform's proxy.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn api.main:create_app --factory --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips '*'"]
