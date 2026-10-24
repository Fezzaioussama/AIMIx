"""Application factory. Run with ``uvicorn api.main:create_app --factory``."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.db import Database
from api.errors import install_error_handlers
from api.frontend import install_frontend
from api.middleware import install_middleware
from api.routes import API_PREFIX, api_router
from api.services.documents.ocr import ocr_config, ocr_engine
from api.services.run_executor import BackgroundRunExecutor
from api.services.runs import interrupt_abandoned_runs
from config.logging_setup import configure_logging
from config.settings import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Runs a previous process left active become resumable before any new one
    starts; on shutdown, active runs are interrupted (and resumable) too."""
    interrupt_abandoned_runs(app.state.database)
    yield
    await asyncio.to_thread(app.state.run_executor.shutdown)


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    # Interactive API docs are a public surface, so they exist only outside production.
    docs = settings.app_env != "production"
    app = FastAPI(
        title="AIMIx API",
        debug=settings.debug,
        docs_url=f"{API_PREFIX}/docs" if docs else None,
        openapi_url=f"{API_PREFIX}/openapi.json" if docs else None,
        swagger_ui_oauth2_redirect_url=f"{API_PREFIX}/docs/oauth2-redirect" if docs else None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.database = Database(settings.database_url)
    # Built once: finding out whether OCR can run here starts a process.
    app.state.ocr = ocr_engine(ocr_config(settings))
    app.state.run_executor = BackgroundRunExecutor(
        settings.run_max_concurrent, settings.run_shutdown_grace_seconds
    )
    install_error_handlers(app)
    install_middleware(app, settings)
    app.include_router(api_router())
    # Last, so its catch-all route never shadows an API route.
    install_frontend(app, settings.frontend_dist_dir)
    return app
