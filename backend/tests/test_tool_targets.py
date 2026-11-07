"""What a run's trace keeps of each tool call besides its name and status: what the
call was about, from the one argument that says it, cut short; never the output."""

from __future__ import annotations

from langchain_core.messages import AIMessage, ToolMessage

from api.services.agent_types import ToolCallTrace
from api.services.multiagent.step_agent import _tool_trace
from api.services.tool_targets import TARGET_MAX_CHARS, call_target


def test_each_built_in_tool_names_the_argument_that_says_what_the_call_is_about() -> None:
    assert call_target("web_search", {"query": " best CRM 2026 ", "max_results": 5}) == (
        "best CRM 2026"
    )
    assert call_target("fetch_url", {"url": "https://example.com/pricing"}) == (
        "https://example.com/pricing"
    )
    assert call_target("ask_user", {"question": "Blue or red?", "options": ["Blue"]}) == (
        "Blue or red?"
    )
    assert call_target("save_artifact", {"path": "notes/plan.md", "content": "secret"}) == (
        "notes/plan.md"
    )


def test_code_is_never_a_subject_and_an_unknown_tool_shows_its_first_text() -> None:
    assert call_target("run_python", {"code": "print(1)"}) == ""
    assert call_target("crm_send_email", {"count": 2, "to": "ada@example.com"}) == (
        "ada@example.com"
    )
    assert call_target("crm_send_email", {"count": 2}) == ""
    assert call_target("web_search", {"query": 42}) == ""
    assert call_target("web_search", {}) == ""


def test_a_long_subject_is_cut_short() -> None:
    target = call_target("web_search", {"query": "x" * 500})

    assert len(target) == TARGET_MAX_CHARS
    assert target.endswith("…")


def test_the_trace_keeps_the_subject_with_the_name_and_status() -> None:
    messages = [
        AIMessage(
            content="",
            tool_calls=[
                {"name": "web_search", "args": {"query": "best CRM"}, "id": "call-1"},
                {"name": "run_python", "args": {"code": "1+1"}, "id": "call-2"},
            ],
        ),
        ToolMessage(content="results", tool_call_id="call-1", status="success"),
        ToolMessage(content="2", tool_call_id="call-2", status="error"),
    ]

    assert _tool_trace(messages) == [
        ToolCallTrace("web_search", "success", "best CRM"),
        ToolCallTrace("run_python", "error"),
    ]
