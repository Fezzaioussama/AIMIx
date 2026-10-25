"""Built-in agent tools: calculator, page text, clock, registry, and use in a run."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from time import perf_counter
from typing import Any

import pytest
from docx import Document
from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import ToolException
from pypdf import PdfReader
from sqlalchemy.orm import Session

from api.models import User
from api.repositories import pipelines
from api.services.artifacts.contracts import RenderOptions
from api.services.catalog import default_model_id
from api.services.documents.contracts import ExtractionLimits
from api.services.documents.extraction import TRUNCATION_NOTE
from api.services.files.storage import WorkspaceStorage
from api.services.llm import LLMProfile
from api.services.multiagent import step_agent
from api.services.toolbox.calculator import evaluate
from api.services.toolbox.config import toolbox_config
from api.services.toolbox.html_text import html_to_text
from api.services.toolbox.registry import toolbox_tools
from api.services.toolbox.tools import calculator_tool, current_datetime_tool
from api.services.toolbox.workspace import LocalWorkspace, WorkspaceLimits
from tests.conftest import TEST_SETTINGS, UNUSED_WORKSPACE, tool_call
from tests.test_documents import make_docx, make_pdf

CONFIG = toolbox_config(TEST_SETTINGS, UNUSED_WORKSPACE)
DOCUMENT_LIMITS = ExtractionLimits(
    max_bytes=100_000,
    max_chars=10_000,
    max_pages=5,
    max_unpacked_bytes=1_000_000,
    max_xml_part_bytes=500_000,
    max_image_pixels=1_000_000,
    max_spreadsheet_rows=100,
    max_ocr_pages=3,
    ocr_max_seconds=60.0,
    ocr_dpi=72,
    max_concurrent=2,
    wait_seconds=5.0,
)
WORKSPACE_LIMITS = WorkspaceLimits(1_000, 500, 20, 10, 5, DOCUMENT_LIMITS)
#: A missing font, so PDFs use the built-in one wherever the tests run.
RENDER = RenderOptions(Path("/no/such/font.ttf"), Path("/no/such/font-bold.ttf"))


def local_workspace(
    root: Path, limits: WorkspaceLimits = WORKSPACE_LIMITS, quota: int = 100_000
) -> LocalWorkspace:
    return LocalWorkspace(WorkspaceStorage(root, quota, max_files=1_000), limits, RENDER)


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


@pytest.mark.parametrize("expression", ["round(5, -10**9)", "round(5, -10**7)", "round(5, 2.5)"])
def test_calculator_refuses_a_rounding_that_would_freeze_the_server(expression: str) -> None:
    # round(5, -n) computes 10**n in one GIL-holding call: 10**7 alone takes seconds.
    started = perf_counter()
    with pytest.raises(ToolException, match="round"):
        evaluate(expression)
    assert perf_counter() - started < 0.5
    assert evaluate("round(123456, -3)") == 123000


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
    workspace = local_workspace(tmp_path)

    assert workspace.list_files() == "notes.md\nsales.csv"
    assert workspace.read_file("notes.md") == "Quarterly revenue grew 12%."
    assert workspace.search_files("REVENUE") == "notes.md:1: Quarterly revenue grew 12%."
    assert workspace.read_csv("sales.csv") == (
        '[{"name": "Alpha", "total": "42"}, {"name": "Beta", "total": "7"}]'
    )


def test_workspace_saves_new_artifacts_without_overwriting(tmp_path: Path) -> None:
    workspace = local_workspace(tmp_path)

    assert workspace.save_artifact("reports/summary.md", "Done") == "Saved reports/summary.md"
    assert (tmp_path / "reports" / "summary.md").read_text() == "Done"
    with pytest.raises(ToolException, match="already exists"):
        workspace.save_artifact("reports/summary.md", "Replace")
    assert (tmp_path / "reports" / "summary.md").read_text() == "Done"


@pytest.mark.parametrize("path", ["../secret.txt", ".env", "/tmp/secret.txt"])
def test_workspace_rejects_paths_outside_the_sandbox(tmp_path: Path, path: str) -> None:
    workspace = local_workspace(tmp_path)

    with pytest.raises(ToolException, match=r"relative to the workspace|outside the workspace"):
        workspace.read_file(path)


def test_workspace_does_not_follow_symlinks(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside.txt"
    outside.write_text("secret")
    (tmp_path / "linked.txt").symlink_to(outside)
    (tmp_path / "inside.txt").write_text("inside")
    (tmp_path / "alias.txt").symlink_to(tmp_path / "inside.txt")
    workspace = local_workspace(tmp_path)

    assert workspace.list_files() == "inside.txt"
    assert workspace.search_files("secret") == "No matches found."
    with pytest.raises(ToolException, match="outside the workspace"):
        workspace.read_file("linked.txt")
    with pytest.raises(ToolException, match="Links are not followed"):
        workspace.read_file("alias.txt")


@pytest.mark.parametrize(("path", "opens"), [("brief.docx", Document), ("brief.pdf", PdfReader)])
def test_save_artifact_lays_markdown_out_as_a_document(
    tmp_path: Path, path: str, opens: type[Any]
) -> None:
    limits = replace(WORKSPACE_LIMITS, max_file_bytes=200_000)
    workspace = local_workspace(tmp_path, limits, quota=1_000_000)

    assert workspace.save_artifact(path, "# Brief\n\nRevenue grew **12%**.") == f"Saved {path}"
    opens(BytesIO((tmp_path / path).read_bytes()))  # a real file of that format
    assert "Revenue grew 12%." in workspace.read_file(path)


def test_save_artifact_writes_html_as_given_and_names_what_it_cannot(tmp_path: Path) -> None:
    workspace = local_workspace(tmp_path)

    workspace.save_artifact("page.html", "<h1>Hi</h1>")
    with pytest.raises(ToolException, match=r"'\.exe' files cannot be saved.*\.docx.*\.pdf"):
        workspace.save_artifact("tool.exe", "MZ")

    assert [path.name for path in tmp_path.iterdir()] == ["page.html"]
    assert (tmp_path / "page.html").read_text() == "<h1>Hi</h1>"


def test_save_artifact_keeps_the_file_size_limit_and_the_quota(tmp_path: Path) -> None:
    (tmp_path / "upload.txt").write_text("x" * 90)
    workspace = local_workspace(tmp_path, quota=100)

    with pytest.raises(ToolException, match=r"larger than the 0\.001 MB file limit"):
        workspace.save_artifact("big.md", "x" * 1_001)
    # The rendered document counts too, not only the Markdown.
    with pytest.raises(ToolException, match="file limit"):
        workspace.save_artifact("small.pdf", "Hello")
    with pytest.raises(ToolException, match="storage limit"):
        workspace.save_artifact("notes.md", "y" * 20)
    assert workspace.save_artifact("notes.md", "y" * 10) == "Saved notes.md"


def test_workspace_reads_pdf_and_word_files_as_text(tmp_path: Path) -> None:
    (tmp_path / "report.pdf").write_bytes(make_pdf(["Revenue grew by ten percent"]))
    (tmp_path / "report.docx").write_bytes(make_docx())
    (tmp_path / "broken.pdf").write_bytes(b"%PDF-1.4 not really")
    workspace = local_workspace(tmp_path)

    assert "Revenue grew by ten percent" in workspace.read_file("report.pdf")
    assert workspace.read_file("report.docx").startswith("Quarterly report")
    with pytest.raises(ToolException, match="could not be read"):
        workspace.read_file("broken.pdf")


def test_a_long_document_is_cut_at_the_output_limit(tmp_path: Path) -> None:
    (tmp_path / "long.pdf").write_bytes(make_pdf(["word " * 60, "more " * 60]))
    workspace = local_workspace(tmp_path, replace(WORKSPACE_LIMITS, max_output_chars=100))

    text = workspace.read_file("long.pdf")

    assert text.endswith(TRUNCATION_NOTE.strip())
    assert len(text) <= 100 + len(TRUNCATION_NOTE)


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
