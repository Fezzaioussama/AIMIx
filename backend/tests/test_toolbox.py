"""Built-in agent tools: calculator, page text, clock, registry, and use in a run."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import ToolException
from sqlalchemy.orm import Session

from api.models import User
from api.repositories import pipelines
from api.services.catalog import default_model_id
from api.services.llm import LLMProfile
from api.services.multiagent import step_agent
from api.services.toolbox.calculator import evaluate
from api.services.toolbox.config import toolbox_config
from api.services.toolbox.html_text import html_to_text
from api.services.toolbox.registry import toolbox_tools
from api.services.toolbox.tools import calculator_tool, current_datetime_tool
from api.services.toolbox.workspace import LocalWorkspace, WorkspaceLimits
from tests.conftest import TEST_SETTINGS, tool_call

CONFIG = toolbox_config(TEST_SETTINGS)
WORKSPACE_LIMITS = WorkspaceLimits(1_000, 500, 20, 10, 5)


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("(1250 * 0.07) / 12", 7.291666666666667),
        ("2 ** 10 - 24 // 5 % 3", 1023),
        ("-sqrt(16) + abs(-2)", -2.0),
        ("round(pi, 2)", 3.14),
    ],
)
def test_calculator_evaluates_arithmetic(expression: str, expected: float) -> None:
    assert evaluate(expression) == pytest.approx(expected)


@pytest.mark.parametrize(
    "expression",
    [
        "__import__('os').system('id')",
        "(1).__class__",
        "True + True",
        "sqrt(x=4)",
        "9 ** 9 ** 9",
        "1 / 0",
        "sqrt(-1)",
        "1 +",
        "1" * 201,
    ],
)
def test_calculator_rejects_unsafe_or_unbounded_input(expression: str) -> None:
    with pytest.raises(ToolException):
        evaluate(expression)


def test_a_tool_error_reaches_the_model_instead_of_aborting() -> None:
    message = calculator_tool().invoke(tool_call("calculator", {"expression": "1 / 0"}))
    assert isinstance(message, ToolMessage)
    assert message.status == "error"
    assert "division by zero" in str(message.content)


def test_html_to_text_keeps_prose_and_drops_scripts() -> None:
    markup = (
        "<html><head><title>Report</title><style>p { color: red }</style></head><body>"
        "<h1>Q3 &amp; Q4</h1><script>alert(1)</script>"
        "<p>Revenue   grew\n by <b>12%</b>.</p><ul><li>One</li><li>Two</li></ul></body></html>"
    )
    assert html_to_text(markup) == "Report\nQ3 & Q4\nRevenue grew by 12%.\nOne\nTwo"


def test_current_datetime_reports_utc_time_and_weekday() -> None:
    fixed = datetime(2026, 10, 18, 9, 30, tzinfo=timezone.utc)
    tool = current_datetime_tool(lambda: fixed)
    assert tool.invoke({}) == "2026-10-18T09:30:00+00:00 (Sunday)"


def test_web_search_is_offered_only_with_a_search_key() -> None:
    assert "web_search" not in [item.name for item in toolbox_tools(CONFIG)]
    keyed = replace(CONFIG, search_api_key="tvly-test")
    assert [item.name for item in toolbox_tools(keyed)] == [
        "web_search",
        "fetch_url",
        "calculator",
        "current_datetime",
    ]


def test_enabled_list_selects_tools_and_ignores_unknown_names() -> None:
    config = replace(CONFIG, enabled=("calculator", "no_such_tool"))
    assert [item.name for item in toolbox_tools(config)] == ["calculator"]


def test_registry_offers_configured_workspace_tools(tmp_path: Path) -> None:
    enabled = (
        "list_workspace_files",
        "read_workspace_file",
        "search_workspace_files",
        "read_csv",
        "save_artifact",
    )
    config = replace(CONFIG, enabled=enabled, workspace_dir=tmp_path)

    assert [item.name for item in toolbox_tools(config)] == list(enabled)


def test_workspace_readers_disable_outbound_tools_without_explicit_opt_in(
    tmp_path: Path,
) -> None:
    enabled = ("fetch_url", "web_search", "read_workspace_file")
    config = replace(CONFIG, enabled=enabled, workspace_dir=tmp_path, search_api_key="key")

    assert [item.name for item in toolbox_tools(config)] == ["read_workspace_file"]

    opted_in = replace(config, allow_workspace_network_access=True)
    assert [item.name for item in toolbox_tools(opted_in)] == [
        "web_search",
        "fetch_url",
        "read_workspace_file",
    ]


def test_workspace_lists_reads_searches_and_parses_csv(tmp_path: Path) -> None:
    (tmp_path / "notes.md").write_text("Quarterly revenue grew 12%.")
    (tmp_path / "sales.csv").write_text("name,total\nAlpha,42\nBeta,7\n")
    workspace = LocalWorkspace(tmp_path, WORKSPACE_LIMITS)

    assert workspace.list_files() == "notes.md\nsales.csv"
    assert workspace.read_file("notes.md") == "Quarterly revenue grew 12%."
    assert workspace.search_files("REVENUE") == "notes.md:1: Quarterly revenue grew 12%."
    assert workspace.read_csv("sales.csv") == (
        '[{"name": "Alpha", "total": "42"}, {"name": "Beta", "total": "7"}]'
    )


def test_workspace_saves_new_artifacts_without_overwriting(tmp_path: Path) -> None:
    workspace = LocalWorkspace(tmp_path, WORKSPACE_LIMITS)

    assert workspace.save_artifact("reports/summary.md", "Done") == "Saved reports/summary.md"
    assert (tmp_path / "reports" / "summary.md").read_text() == "Done"
    with pytest.raises(ToolException, match="already exists"):
        workspace.save_artifact("reports/summary.md", "Replace")


@pytest.mark.parametrize("path", ["../secret.txt", ".env", "/tmp/secret.txt"])
def test_workspace_rejects_paths_outside_the_sandbox(tmp_path: Path, path: str) -> None:
    workspace = LocalWorkspace(tmp_path, WORKSPACE_LIMITS)

    with pytest.raises(ToolException, match=r"relative to the workspace|outside the workspace"):
        workspace.read_file(path)


def test_workspace_does_not_follow_symlinks(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside.txt"
    outside.write_text("secret")
    (tmp_path / "linked.txt").symlink_to(outside)
    workspace = LocalWorkspace(tmp_path, WORKSPACE_LIMITS)

    assert workspace.list_files() == "No files found."
    assert workspace.search_files("secret") == "No matches found."
    with pytest.raises(ToolException, match="outside the workspace"):
        workspace.read_file("linked.txt")


def test_pipeline_agent_uses_built_in_tools_and_survives_a_failing_one(
    auth_client: TestClient,
    session: Session,
    user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved = pipelines.create_with_steps(
        session,
        user,
        pipelines.PipelineChanges(
            "Budget",
            steps=[
                {"order": 1, "stage": 1, "prompt": "Total {input}", "model": default_model_id()}
            ],
        ),
    )
    calls = [
        {"name": "calculator", "args": {"expression": "40 + 2"}, "id": "call-1"},
        # Refused before any request is sent: the address is not public.
        {"name": "fetch_url", "args": {"url": "http://127.0.0.1/admin"}, "id": "call-2"},
    ]
    model = FakeMessagesListChatModel(
        responses=[AIMessage(content="", tool_calls=calls), AIMessage(content="Total is 42.")]
    )

    def agent_model(profile: LLMProfile, model_id: str | None = None) -> Any:
        return model

    monkeypatch.setattr(FakeMessagesListChatModel, "bind_tools", lambda self, tools, **kw: self)
    monkeypatch.setattr(step_agent, "get_agent_model", agent_model)

    response = auth_client.post(f"/api/pipelines/{saved.id}/run", json={"input": "the costs"})

    assert response.status_code == 200
    assert response.json()["final_output"] == "Total is 42."
    assert response.json()["intermediate_results"][0]["tool_calls"] == [
        {"name": "calculator", "status": "success"},
        {"name": "fetch_url", "status": "error"},
    ]
