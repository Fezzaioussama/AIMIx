"""The chat builds and changes workflows with the Missions planner, and saves them
like the pipeline endpoints do."""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi import FastAPI
from langchain_core.tools import BaseTool, ToolException
from sqlalchemy.orm import Session

from api.models import Pipeline, User
from api.repositories import pipelines, users
from api.repositories.pipelines import PipelineChanges
from api.security import hash_password
from api.services.catalog import default_model_id
from api.services.chat_events import tool_finished
from api.services.chat_tools.workflows import workflow_tools
from api.services.final_check import FINAL_CHECK_ROLE
from tests.chat_fakes import by_name, chat_scope
from tests.conftest import FakeProvider

REQUEST = "Every Monday, a digest of this week's AI news for my team, in French"
PLAN = {
    "name": "AI news digest",
    "steps": [
        {
            "title": "News research",
            "role": "Researcher",
            "stage": 1,
            "prompt": "Find this week's AI news: {input}",
            "allowed_tools": ["web_search"],
        },
        {
            "title": "Digest",
            "role": "Writer",
            "stage": 2,
            "prompt": "Write the digest in French from {input}",
            "is_output": True,
        },
    ],
}


def tools_for(app: FastAPI, user: User, planner: FakeProvider) -> dict[str, BaseTool]:
    return by_name(workflow_tools(chat_scope(app, user, planner)))


def saved_digest(session: Session, user: User) -> Pipeline:
    step = {"order": 1, "stage": 1, "title": "Digest", "prompt": "Summarise {input}"}
    return pipelines.create_with_steps(
        session,
        user,
        PipelineChanges("AI news digest", inputs=[], steps=[{**step, "model": default_model_id()}]),
    )


def test_design_workflow_plans_like_missions_and_saves_the_team(
    app: FastAPI, session: Session, user: User
) -> None:
    planner = FakeProvider(reply=json.dumps(PLAN))

    team = tools_for(app, user, planner)["design_workflow"].invoke({"description": REQUEST})

    prompt, _ = planner.calls[0]
    assert REQUEST in prompt
    assert "web_search" in prompt  # the planner is offered the person's own tools
    saved = pipelines.get_owned(session, user, team["id"])
    assert (team["name"], saved.name) == ("AI news digest", "AI news digest")
    assert [agent["title"] for agent in team["agents"]][:2] == ["News research", "Digest"]
    assert team["agents"][0]["tools"] == ["web_search"]
    assert team["agents"][1]["tools"] == "all"
    # The team ends with the final check, as a mission's does.
    assert team["agents"][-1]["role"] == FINAL_CHECK_ROLE
    assert len(saved.steps) == len(team["agents"])


def test_a_designed_workflow_links_to_its_mission() -> None:
    event = tool_finished("design_workflow", {"id": 7, "name": "AI news digest", "agents": []})

    assert event.action == {
        "kind": "pipeline",
        "id": 7,
        "title": "AI news digest",
        "subtitle": "Open the mission",
    }


def test_change_workflow_revises_the_saved_team_and_lists_what_changed(
    app: FastAPI, session: Session, user: User
) -> None:
    saved = saved_digest(session, user)
    revised = {
        "name": "AI news digest",
        "steps": [
            {"title": "Digest", "stage": 1, "prompt": "Summarise {input}"},
            {
                "title": "Fact check",
                "role": "Fact checker",
                "stage": 2,
                "prompt": "Check every claim in {input}",
                "is_output": True,
            },
        ],
    }
    planner = FakeProvider(reply=json.dumps(revised))

    result = tools_for(app, user, planner)["change_workflow"].invoke(
        {"pipeline_id": saved.id, "change": "Add an agent that checks the facts"}
    )

    prompt, _ = planner.calls[0]
    assert "Add an agent that checks the facts" in prompt
    assert "Summarise {input}" in prompt  # the planner revises the saved team
    assert [agent["title"] for agent in result["agents"]] == ["Digest", "Fact check"]
    assert {"target": "step", "kind": "added", "label": "Fact check"}.items() <= next(
        change for change in result["changes"] if change["kind"] == "added"
    ).items()
    session.expire_all()
    assert [step.title for step in pipelines.get_owned(session, user, saved.id).steps] == [
        "Digest",
        "Fact check",
    ]


def test_change_workflow_cannot_reach_another_persons_workflow(
    app: FastAPI, session: Session, user: User
) -> None:
    stranger = users.create(session, "stranger", hash_password("password-123", 1))
    theirs = saved_digest(session, stranger)
    planner = FakeProvider(reply=json.dumps(PLAN))

    with pytest.raises(ToolException, match="not found"):
        tools_for(app, user, planner)["change_workflow"].invoke(
            {"pipeline_id": theirs.id, "change": "Rename it"}
        )
    assert planner.calls == []


def test_a_plan_the_planner_cannot_give_is_explained_and_nothing_is_saved(
    app: FastAPI, session: Session, user: User
) -> None:
    planner = FakeProvider(reply="Sorry, I cannot help with that.")

    with pytest.raises(ToolException):
        tools_for(app, user, planner)["design_workflow"].invoke({"description": REQUEST})
    assert len(planner.calls) == 2  # asked once more, as Missions does
    assert pipelines.for_user(session, user) == []


def test_list_tools_shows_what_the_persons_agents_can_use(app: FastAPI, user: User) -> None:
    listing: Any = tools_for(app, user, FakeProvider())["list_tools"].invoke({})

    assert listing == [{"name": "web_search", "description": "Search the web", "source": "AIMIx"}]
