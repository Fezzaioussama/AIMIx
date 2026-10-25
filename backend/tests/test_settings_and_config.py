"""Configuration guarantees: nothing secret or environment-specific in code."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from api.exceptions import DomainError
from config.settings import LOCAL_SECRET_KEY, Settings
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
    assert set(TEST_SETTINGS.llm_api_keys) == {"openrouter", "togetherai"}


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


@pytest.mark.parametrize(
    "values",
    [
        {"secret_key": ""},
        {"secret_key": "k", "debug": True},
        {"secret_key": "k", "allowed_hosts": ""},
        {"secret_key": "k", "integrations_allow_private_network": True},
    ],
)
def test_production_refuses_unsafe_configuration(values: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        settings(app_env="production", **values)


def test_production_turns_on_hsts() -> None:
    from api.middleware import HSTS_HEADER

    assert settings(app_env="production", secret_key="k").app_env == "production"
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
