"""Test settings: deterministic, offline, and fast.

No .env value may change the outcome of a test run, so the LLM layer is left
unconfigured on purpose — tests inject fake providers.
"""

from __future__ import annotations

from config.settings.base import *  # noqa: F403

DEBUG = False
SECRET_KEY = "testing-key-not-used-outside-tests"
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]

DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}

# Hashing is the slowest part of auth-heavy tests.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

LLM_PROVIDER = "openrouter"
LLM_TIMEOUT_SECONDS = 1.0
LLM_API_KEYS = {"openrouter": "", "togetherai": ""}
LLM_BASE_URLS = {"openrouter": "", "togetherai": ""}

LOGGING = {"version": 1, "disable_existing_loggers": False, "root": {"handlers": []}}
