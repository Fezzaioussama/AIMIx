"""Managing everything else by chat: runs (follow, stop, resume), ready-made workflows,
and the model and connected apps, with the same rules as their screens."""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi import FastAPI
from langchain_core.tools import ToolException
from sqlalchemy.orm import Session

from api.exceptions import NotFound, RunStillRunning
from api.models import Integration, Pipeline, User
from api.repositories import pipelines, users
from api.repositories.pipelines import PipelineChanges
from api.security import hash_password, secret_box_for
from api.services import llm_settings
from api.services.agent_tools import built_in_tools
from api.services.catalog import available_model_ids, default_model_id
from api.services.chat_events import tool_finished
from api.services.chat_tools import runs as chat_runs
from api.services.chat_tools.runs import run_tools
from api.services.chat_tools.settings import settings_tools
from api.services.chat_tools.templates import template_tools
from api.services.runs import RunService, RunStart
from api.services.templates.registry import all_templates
from tests.approval_fakes import request_approval, running_run
from tests.chat_fakes import by_name, chat_scope
from tests.conftest import TEST_SETTINGS, FakeProvider, InlineRunExecutor


def saved_pipeline(session: Session, user: User, name: str = "Digest") -> Pipeline:
    step = {"order": 1, "stage": 1, "title": "Digest", "prompt": "Summarise {input}"}
    return pipelines.create_with_steps(
        session,
        user,
        PipelineChanges(name, inputs=[], steps=[{**step, "model": default_model_id()}]),
    )


def finished_run(app: FastAPI, session: Session, user: User, reply: str) -> int:
    service = RunService(app.state.database, InlineRunExecutor(), max_parallel_steps=1)
    pipeline = saved_pipeline(session, user)
    return service.start(user, pipeline, RunStart("news"), FakeProvider(reply=reply)).run.id


# --- runs -------------------------------------------------------------------


def test_the_chat_lists_runs_and_tells_what_one_made(
    app: FastAPI, session: Session, user: User
) -> None:
    run_id = finished_run(app, session, user, reply="Monday's digest")
    tools = by_name(run_tools(chat_scope(app, user)))

    listing = tools["list_runs"].invoke({})
    details = tools["get_run"].invoke({"run_id": run_id})

    assert [(item["id"], item["workflow"], item["status"]) for item in listing] == [
        (run_id, "Digest", "succeeded")
    ]
    assert listing[0]["started_by"] == "manual"
    assert "Monday's digest" in details["result"]
    assert (details["result_cut"], details["waiting_for_your_ok"]) == (False, [])
    assert details["agents"] == [{"title": "Digest", "status": "succeeded"}]
    assert tools["list_runs"].invoke({"status": "failed"}) == []


def test_a_long_result_is_cut_for_the_chat(
    app: FastAPI, session: Session, user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_id = finished_run(app, session, user, reply="x" * 50)
    limited = TEST_SETTINGS.model_copy(update={"chat_run_result_max_chars": 7})
    monkeypatch.setattr(chat_runs, "get_settings", lambda: limited)

    details = by_name(run_tools(chat_scope(app, user)))["get_run"].invoke({"run_id": run_id})

    assert (details["result"], details["result_cut"]) == ("x" * 7, True)


def test_another_persons_run_and_an_unknown_status_are_refused(
    app: FastAPI, session: Session, user: User
) -> None:
    stranger = users.create(session, "stranger", hash_password("password-123", 1))
    theirs = finished_run(app, session, stranger, reply="private")
    tools = by_name(run_tools(chat_scope(app, user)))

    assert tools["list_runs"].invoke({}) == []
    with pytest.raises(ToolException, match="not found"):
        tools["get_run"].invoke({"run_id": theirs})
    with pytest.raises(ToolException):
        tools["stop_run"].invoke({"run_id": theirs})
    with pytest.raises(ToolException):
        tools["list_runs"].invoke({"status": "exploded"})


def test_a_waiting_run_is_shown_then_stopped_and_resumed(
    app: FastAPI, session: Session, user: User
) -> None:
    run_id = running_run(app.state.database, user, saved_pipeline(session, user))
    request_approval(session, run_id)
    tools = by_name(run_tools(chat_scope(app, user, agent=FakeProvider(reply="done"))))

    assert tools["get_run"].invoke({"run_id": run_id})["waiting_for_your_ok"] == ["crm_send_email"]
    stopped = tools["stop_run"].invoke({"run_id": run_id})
    resumed = tools["resume_run"].invoke({"run_id": run_id})

    assert (stopped["status"], stopped["waiting_for_your_ok"]) == ("cancelled", [])
    assert resumed["status"] == "succeeded"
    assert tool_finished("resume_run", resumed).action == {
        "kind": "run",
        "id": run_id,
        "title": "Digest",
        "subtitle": "Finished",
    }


def test_a_run_too_long_to_wait_for_goes_on_and_links_to_itself(app: FastAPI, user: User) -> None:
    def still_running(pipeline_id: int, start: RunStart) -> Any:
        raise RunStillRunning(42, 300)

    def unknown(pipeline_id: int, start: RunStart) -> Any:
        raise NotFound(f"Pipeline {pipeline_id} was not found.")

    scope = chat_scope(app, user)
    waits = by_name(built_in_tools(app.state.database, user, still_running, scope.schedules))
    refuses = by_name(built_in_tools(app.state.database, user, unknown, scope.schedules))

    answer = waits["run_pipeline"].invoke({"pipeline_id": 1, "input_text": "go"})
    assert answer == {"id": 42, "status": "running"}
    assert tool_finished("run_pipeline", answer).action == {
        "kind": "run",
        "id": 42,
        "title": "Run",
        "subtitle": "Running",
    }
    with pytest.raises(ToolException, match="not found"):
        refuses["run_pipeline"].invoke({"pipeline_id": 1, "input_text": "go"})


# --- ready-made workflows ---------------------------------------------------


def test_the_chat_starts_a_workflow_from_a_ready_made_one(
    app: FastAPI, session: Session, user: User
) -> None:
    template = all_templates()[0]
    tools = by_name(template_tools(chat_scope(app, user)))

    listed = tools["list_templates"].invoke({})
    team = tools["use_template"].invoke({"slug": template.slug, "name": "My research"})

    assert template.slug in [item["slug"] for item in listed]
    assert listed[0]["agents"] == template.step_count
    saved = pipelines.get_owned(session, user, team["id"])
    assert (team["name"], saved.name) == ("My research", "My research")
    assert len(team["agents"]) == template.step_count
    assert tool_finished("use_template", team).action is not None
    with pytest.raises(ToolException, match="not found"):
        tools["use_template"].invoke({"slug": "no-such-template"})


# --- model and connected apps -------------------------------------------------


def save_key(session: Session, user: User, provider: str = "openrouter") -> None:
    choice = llm_settings.ProviderChoice(provider, available_model_ids(provider)[0], "sk-test-9876")
    update = llm_settings.SettingsUpdate(provider, [choice])
    llm_settings.save(session, user, secret_box_for(TEST_SETTINGS), update)


def test_settings_show_the_model_and_apps_but_never_a_key_or_an_address(
    app: FastAPI, session: Session, user: User
) -> None:
    save_key(session, user)
    session.add(
        Integration(user_id=user.id, name="crm", url="https://mcp.example.com/sse?token=secret-123")
    )
    session.commit()

    shown = by_name(settings_tools(chat_scope(app, user)))["show_settings"].invoke({})

    assert shown["provider"] == "openrouter"
    keys = {item["name"]: item["has_key"] for item in shown["providers"]}
    assert (keys["openrouter"], keys["meta"]) == (True, False)
    assert shown["connected_apps"] == [
        {"name": "crm", "host": "mcp.example.com", "on": True, "asks_first": True}
    ]
    assert "secret-123" not in json.dumps(shown)
    assert "9876" not in json.dumps(shown)


def test_the_chat_changes_the_default_model_within_what_settings_allow(
    app: FastAPI, session: Session, user: User
) -> None:
    save_key(session, user)
    other = available_model_ids("openrouter")[1]
    tool = by_name(settings_tools(chat_scope(app, user)))["set_default_model"]

    changed = tool.invoke({"model": other})

    assert (changed["provider"], changed["default_model"]) == ("openrouter", other)
    session.expire_all()
    saved = {item.name: item for item in llm_settings.read(session, user).providers}
    assert (saved["openrouter"].default_model, saved["openrouter"].key_source) == (other, "saved")
    with pytest.raises(ToolException, match="no API key"):
        tool.invoke({"model": available_model_ids("meta")[0], "provider": "meta"})
    with pytest.raises(ToolException):
        tool.invoke({"model": "made-up/model"})
