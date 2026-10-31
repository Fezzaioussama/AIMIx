"""Configuration guarantees: nothing secret or environment-specific in code."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from api.exceptions import DomainError
from config.settings import (
    LOCAL_SECRET_KEY,
    MIN_PRODUCTION_HASH_ITERATIONS,
    MIN_PRODUCTION_SECRET_KEY_LENGTH,
    Settings,
)
from tests.conftest import TEST_SETTINGS

BACKEND_DIR = Path(__file__).resolve().parents[1]


def settings(**values: object) -> Settings:
    """Settings from explicit values only — no .env file."""
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


def test_no_provider_base_url_is_hard_coded_outside_the_provider_module() -> None:
    """§1.8 — the OpenRouter URL lives in one provider module as a documented
    default that settings can override."""
    offenders = []
    for path in [*(BACKEND_DIR / "api").rglob("*.py"), BACKEND_DIR / "llm" / "base.py"]:
        if "https://" in path.read_text():
            offenders.append(str(path.relative_to(BACKEND_DIR)))
    assert offenders == []


def test_provider_settings_come_from_configuration() -> None:
    assert isinstance(TEST_SETTINGS.llm_timeout_seconds, float)
    assert TEST_SETTINGS.llm_timeout_seconds > 0
    assert set(TEST_SETTINGS.llm_api_keys) == {"openrouter", "togetherai", "meta"}


def test_the_error_handler_is_wired_in(app: FastAPI) -> None:
    assert DomainError in app.exception_handlers


def test_request_urls_stay_out_of_the_logs() -> None:
    """httpx and the MCP client log every URL at INFO; users' URLs may hold a token."""
    import logging

    from config.logging_setup import configure_logging

    configure_logging("INFO")
    try:
        assert logging.getLogger("api.services").isEnabledFor(logging.INFO)
        for name in ("httpx", "mcp.client.streamable_http"):
            assert not logging.getLogger(name).isEnabledFor(logging.INFO)
    finally:
        configure_logging(TEST_SETTINGS.log_level)


def test_no_logging_is_configured_at_import_time_in_the_llm_package() -> None:
    """basicConfig used to run on import and write to a relative app.log path."""
    assert "basicConfig" not in (BACKEND_DIR / "llm" / "base.py").read_text()


@pytest.mark.parametrize("placeholder", ["your_api_key_here", "change-me", "YOUR-API-KEY"])
def test_placeholder_credentials_are_treated_as_unset(placeholder: str) -> None:
    """A half-filled .env must fail fast rather than send a doomed request."""
    assert settings(OPEN_ROUTER_KEY=placeholder).openrouter_api_key == ""
    assert settings(OPEN_ROUTER_KEY="sk-a-real-looking-key").openrouter_api_key == (
        "sk-a-real-looking-key"
    )
    assert settings(TAVILY_API_KEY=placeholder).tavily_api_key == ""


def test_the_environment_llm_key_is_not_shared_with_accounts_unless_allowed() -> None:
    assert settings().allow_server_llm_key is False
    assert settings(ALLOW_SERVER_LLM_KEY="true").allow_server_llm_key is True


def test_builtin_agent_tools_are_a_comma_list() -> None:
    chosen = settings(AGENT_BUILTIN_TOOLS="calculator, current_datetime")
    assert chosen.agent_builtin_tools == ["calculator", "current_datetime"]
    assert settings(AGENT_BUILTIN_TOOLS="").agent_builtin_tools == []


def test_upload_extensions_are_lower_case_with_a_dot() -> None:
    chosen = settings(WORKSPACE_UPLOAD_EXTENSIONS="PDF, .Docx ,md")
    assert chosen.workspace_upload_extensions == [".pdf", ".docx", ".md"]


def test_relative_agent_workspace_is_resolved_from_backend() -> None:
    assert settings(AGENT_WORKSPACE_DIR="agent-files").workspace_dir == BACKEND_DIR / "agent-files"


def test_legacy_django_variable_names_still_work() -> None:
    legacy = settings(DJANGO_SECRET_KEY="legacy-key", DJANGO_ALLOWED_HOSTS="a.example, b.example")
    assert legacy.secret_key == "legacy-key"
    assert legacy.allowed_hosts == ["a.example", "b.example"]


def test_local_development_gets_a_throwaway_key() -> None:
    assert settings(app_env="local", secret_key="").secret_key == LOCAL_SECRET_KEY


#: Long enough for production.
PRODUCTION_KEY = "p" * MIN_PRODUCTION_SECRET_KEY_LENGTH


@pytest.mark.parametrize(
    ("values", "problem"),
    [
        ({"secret_key": ""}, "SECRET_KEY must be set"),
        ({"debug": True}, "DEBUG"),
        ({"allowed_hosts": ""}, "ALLOWED_HOSTS"),
        ({"integrations_allow_private_network": True}, "INTEGRATIONS_ALLOW_PRIVATE_NETWORK"),
        ({"secret_key": "p" * 31}, "at least 32 characters"),
        ({"secret_key": LOCAL_SECRET_KEY}, "local development key"),
        ({"password_hash_iterations": 599_999}, "PASSWORD_HASH_ITERATIONS"),
    ],
)
def test_production_refuses_unsafe_configuration(values: dict[str, object], problem: str) -> None:
    with pytest.raises(ValidationError, match=problem):
        settings(app_env="production", **{"secret_key": PRODUCTION_KEY, **values})


def test_production_accepts_a_long_key_and_the_default_work_factor() -> None:
    chosen = settings(app_env="production", secret_key=PRODUCTION_KEY)
    assert chosen.password_hash_iterations >= MIN_PRODUCTION_HASH_ITERATIONS


def test_the_iteration_floor_applies_to_production_only() -> None:
    assert settings(app_env="local", password_hash_iterations=1).password_hash_iterations == 1


def startup_warnings(secret_key: str, caplog: pytest.LogCaptureFixture) -> list[str]:
    """What ``create_app`` warns about with this key. The handler sits on the app's
    own logger: ``create_app`` reconfigures the root one."""
    from api.main import create_app
    from config.settings import pin_settings

    main_logger = logging.getLogger("api.main")
    main_logger.addHandler(caplog.handler)
    pin_settings(TEST_SETTINGS.model_copy(update={"secret_key": secret_key}))
    try:
        create_app()
    finally:
        pin_settings(TEST_SETTINGS)
        main_logger.removeHandler(caplog.handler)
    return [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]


def test_the_local_development_key_is_announced_at_startup(
    caplog: pytest.LogCaptureFixture,
) -> None:
    warnings = startup_warnings(LOCAL_SECRET_KEY, caplog)
    assert any("settings.local_secret_key" in message for message in warnings)


def test_a_configured_key_is_not_announced(caplog: pytest.LogCaptureFixture) -> None:
    warnings = startup_warnings(TEST_SETTINGS.secret_key, caplog)
    assert not any("local_secret_key" in message for message in warnings)


def test_auth_hardening_settings_have_safe_defaults() -> None:
    defaults = settings()
    assert defaults.trusted_proxy_hops == 0
    assert defaults.secret_key_fallbacks == []
    assert defaults.auth_account_failure_limit == 10
    assert defaults.auth_account_failure_window_seconds == 900
    assert settings(SECRET_KEY_FALLBACKS="old-a, old-b").secret_key_fallbacks == ["old-a", "old-b"]
    with pytest.raises(ValidationError):
        settings(TRUSTED_PROXY_HOPS="-1")


def test_production_turns_on_hsts() -> None:
    from api.middleware import HSTS_HEADER

    assert settings(app_env="production", secret_key=PRODUCTION_KEY).app_env == "production"
    assert "Strict-Transport-Security" in HSTS_HEADER


def test_a_run_has_no_cost_limit_unless_one_is_configured() -> None:
    assert settings().run_default_max_cost_usd is None
    assert settings(run_default_max_cost_usd=0.5).run_default_max_cost_usd == 0.5


def test_the_default_run_limit_is_read_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RUN_DEFAULT_MAX_COST_USD", "2.5")
    assert settings().run_default_max_cost_usd == 2.5
    # An empty value, as .env.example ships it, means no limit.
    monkeypatch.setenv("RUN_DEFAULT_MAX_COST_USD", "")
    assert settings().run_default_max_cost_usd is None
    monkeypatch.setenv("RUN_DEFAULT_MAX_COST_USD", "  ")
    assert settings().run_default_max_cost_usd is None


@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf", "lots"])
def test_a_default_run_limit_that_cannot_be_met_stops_the_server_starting(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("RUN_DEFAULT_MAX_COST_USD", value)
    with pytest.raises(ValidationError):
        settings()
