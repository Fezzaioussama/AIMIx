"""Settings shared by every environment. Values come from the environment with
documented defaults in backend/.env.example (AGENTS.md §6); nothing
business-specific or secret is hard-coded here.
"""

from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

# backend/config/settings/base.py -> backend/
BASE_DIR = Path(__file__).resolve().parents[2]

load_dotenv(BASE_DIR / ".env")


def env_str(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


#: Values that look like a filled-in credential but are not one. Treating these
#: as unset means a half-configured .env fails fast with "not configured"
#: instead of sending a doomed request and reporting an upstream 401.
SECRET_PLACEHOLDERS = frozenset(
    {
        "change-me",
        "changeme",
        "your-api-key",
        "your-api-key-here",
        "your_api_key",
        "your_api_key_here",
    }
)


def env_secret(name: str, default: str = "") -> str:
    """Read a credential, treating placeholder values as absent."""
    value = env_str(name, default)
    return "" if value.lower() in SECRET_PLACEHOLDERS else value


def env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError as cause:
        raise ValueError(f"{name} must be a number, got {raw!r}.") from cause


SECRET_KEY = env_str("DJANGO_SECRET_KEY")
DEBUG = env_bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "corsheaders",
    "api",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / env_str("DJANGO_DB_NAME", "db.sqlite3"),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

CORS_ALLOWED_ORIGINS = env_list(
    "DJANGO_CORS_ALLOWED_ORIGINS",
    "http://localhost:4200,http://127.0.0.1:4200",
)

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    # Auth-protected by default; a public endpoint opts out explicitly (§6).
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    # One error shape for every endpoint (§6).
    "EXCEPTION_HANDLER": "api.errors.exception_handler",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env_float("JWT_ACCESS_MINUTES", 60)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env_float("JWT_REFRESH_DAYS", 1)),
    "ROTATE_REFRESH_TOKENS": False,
    "BLACKLIST_AFTER_ROTATION": True,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": SECRET_KEY,
    "VERIFYING_KEY": None,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
    "AUTH_TOKEN_CLASSES": ("rest_framework_simplejwt.tokens.AccessToken",),
    "TOKEN_TYPE_CLAIM": "token_type",
}

# --- LLM provider layer -----------------------------------------------------
# The llm package never reads the environment itself; these values are handed
# to it by api.services.llm (§5 D).
LLM_PROVIDER = env_str("LLM_PROVIDER", "openrouter")
LLM_TIMEOUT_SECONDS = env_float("LLM_TIMEOUT_SECONDS", 60.0)
# Upper bound on provider calls one pipeline run makes at once for a stage whose
# steps run in parallel.
PIPELINE_MAX_PARALLEL_STEPS = max(1, int(env_float("PIPELINE_MAX_PARALLEL_STEPS", 4)))
LLM_API_KEYS = {
    "openrouter": env_secret("OPEN_ROUTER_KEY") or env_secret("OPENROUTER_API_KEY"),
    "togetherai": env_secret("TOGAI_API_KEY"),
}
LLM_BASE_URLS = {
    "openrouter": env_str("OPENROUTER_BASE_URL"),
    "togetherai": env_str("TOGETHERAI_BASE_URL"),
}
LLM_DEFAULT_MODELS = {
    "openrouter": env_str("OPENROUTER_DEFAULT_MODEL", "deepseek/deepseek-v4-flash"),
    "togetherai": env_str(
        "TOGETHERAI_DEFAULT_MODEL", "meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8"
    ),
}

LOG_LEVEL = env_str("DJANGO_LOG_LEVEL", "INFO").upper()

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "standard"},
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {
        "api": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
        "llm": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
    },
}
