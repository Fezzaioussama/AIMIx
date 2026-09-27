"""Application factory. Run with ``uvicorn api.main:create_app --factory``."""

from __future__ import annotations

from fastapi import FastAPI

from api.db import Database
from api.errors import install_error_handlers
from api.middleware import install_middleware
from api.routes import API_PREFIX, api_router
from config.logging_setup import configure_logging
from config.settings import get_settings


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
    )
    app.state.database = Database(settings.database_url)
    install_error_handlers(app)
    install_middleware(app, settings)
    app.include_router(api_router())
    return app
