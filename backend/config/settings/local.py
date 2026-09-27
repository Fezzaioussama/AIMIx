"""Development settings. Used by manage.py unless DJANGO_SETTINGS_MODULE says
otherwise."""

from __future__ import annotations

from config.settings.base import *  # noqa: F403
from config.settings.base import env_bool, env_str

DEBUG = env_bool("DJANGO_DEBUG", default=True)

# A throwaway key is acceptable only here; production.py refuses to start
# without a real one.
SECRET_KEY = env_str("DJANGO_SECRET_KEY") or "django-insecure-local-development-key-change-me"
