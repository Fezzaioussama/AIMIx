"""Configuration guarantees: nothing secret or environment-specific in code."""

from __future__ import annotations

from pathlib import Path

from django.conf import settings

BACKEND_DIR = Path(__file__).resolve().parents[1]


def test_no_provider_base_url_is_hard_coded_outside_the_provider_module() -> None:
    """§1.8 — the OpenRouter URL used to sit in the middle of the transport code.

    It now lives in one provider module as a documented default that settings
    can override.
    """
    offenders = []
    for path in [*(BACKEND_DIR / "api").rglob("*.py"), BACKEND_DIR / "llm" / "base.py"]:
        if "https://" in path.read_text():
            offenders.append(str(path.relative_to(BACKEND_DIR)))
    assert offenders == []


def test_provider_settings_come_from_configuration() -> None:
    assert isinstance(settings.LLM_TIMEOUT_SECONDS, float)
    assert settings.LLM_TIMEOUT_SECONDS > 0
    assert set(settings.LLM_API_KEYS) == {"openrouter", "togetherai"}


def test_the_error_handler_is_wired_in() -> None:
    assert settings.REST_FRAMEWORK["EXCEPTION_HANDLER"] == "api.errors.exception_handler"


def test_endpoints_are_authenticated_by_default() -> None:
    assert settings.REST_FRAMEWORK["DEFAULT_PERMISSION_CLASSES"] == (
        "rest_framework.permissions.IsAuthenticated",
    )


def test_no_logging_is_configured_at_import_time_in_the_llm_package() -> None:
    """basicConfig used to run on import and write to a relative app.log path."""
    assert "basicConfig" not in (BACKEND_DIR / "llm" / "base.py").read_text()


def test_placeholder_credentials_are_treated_as_unset() -> None:
    """A half-filled .env must fail fast rather than send a doomed request.

    Left unhandled, "your_api_key_here" is a non-empty string, so the provider
    builds happily and the caller gets an upstream 401 surfaced as a 502.
    """
    import os

    from config.settings.base import env_secret

    original = os.environ.get("PROBE_SECRET")
    try:
        for placeholder in ("your_api_key_here", "change-me", "YOUR-API-KEY"):
            os.environ["PROBE_SECRET"] = placeholder
            assert env_secret("PROBE_SECRET") == "", placeholder
        os.environ["PROBE_SECRET"] = "sk-a-real-looking-key"
        assert env_secret("PROBE_SECRET") == "sk-a-real-looking-key"
    finally:
        if original is None:
            os.environ.pop("PROBE_SECRET", None)
        else:
            os.environ["PROBE_SECRET"] = original
