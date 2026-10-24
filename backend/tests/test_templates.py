"""Mission templates: every template is a valid pipeline, the gallery lists
them, and using one creates the caller's own pipeline on their default model,
with only the tools they have."""

from __future__ import annotations

import re
from dataclasses import asdict
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.deps import llm_profile, pipeline_tool_catalog
from api.exceptions import NotFound
from api.models import (
    PIPELINE_INPUT_DESCRIPTION_MAX_LENGTH,
    PIPELINE_INPUT_LABEL_MAX_LENGTH,
    PIPELINE_NAME_MAX_LENGTH,
    RESERVED_INPUT_NAME,
    STEP_EXPECTED_OUTPUT_MAX_LENGTH,
    STEP_ROLE_MAX_LENGTH,
    STEP_TITLE_MAX_LENGTH,
    Pipeline,
    User,
)
from api.repositories import users
from api.schemas.pipelines import PipelineIn
from api.security import hash_password
from api.services.agent_types import ToolDescriptor
from api.services.catalog import available_model_ids
from api.services.llm import LLMProfile
from api.services.prompts import PLACEHOLDER
from api.services.templates.contracts import MissionTemplate
from api.services.templates.registry import CATALOGUE, TEMPLATES, get_template
from api.services.templates.review import REVIEWER_ROLE
from api.services.templates.use import StepDefaults, TemplateChoice, template_steps, use_template
from api.services.toolbox.registry import TOOLBOX
from tests.conftest import FakeProvider, bearer

EVERY_TOOL = list(TOOLBOX)
STAGE_INPUT = f"{{{RESERVED_INPUT_NAME}}}"


def slug_of(template: MissionTemplate) -> str:
    return template.slug


each_template = pytest.mark.parametrize("template", CATALOGUE, ids=slug_of)


def placeholders(prompt: str) -> set[str]:
    return set(PLACEHOLDER.findall(prompt))


class FakeCatalog:
    """Stands in for tool discovery, reporting these tool names as available."""

    def __init__(self, names: list[str]) -> None:
        self.names = names

    def available_sync(self) -> list[ToolDescriptor]:
        return [ToolDescriptor(name, f"{name} tool", "AIMIx") for name in self.names]


def use_tools(app: FastAPI, names: list[str]) -> None:
    app.dependency_overrides[pipeline_tool_catalog] = lambda: FakeCatalog(names)


def step_tools(body: dict[str, Any]) -> list[list[str] | None]:
    return [step["allowed_tools"] for step in body["steps"]]


# --- The catalogue -------------------------------------------------------------


def test_the_catalogue_holds_eight_templates_with_unique_slugs() -> None:
    assert len(CATALOGUE) == 8
    assert len(TEMPLATES) == len(CATALOGUE)
    for template in CATALOGUE:
        assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", template.slug)
        assert template.title and template.description


@each_template
def test_a_template_passes_the_validation_of_a_saved_pipeline(
    template: MissionTemplate, default_model: str
) -> None:
    plan = {
        "name": template.title,
        "inputs": [asdict(field) for field in template.inputs],
        "steps": template_steps(template, [default_model], EVERY_TOOL),
    }
    saved = PipelineIn.model_validate(plan)
    assert [step.order for step in saved.steps] == list(range(1, len(template.steps) + 1))


@each_template
def test_a_template_fits_every_field_limit_without_clipping(template: MissionTemplate) -> None:
    # The sanitiser would silently cut an overlong value, so check the source.
    assert len(template.title) <= PIPELINE_NAME_MAX_LENGTH
    for field in template.inputs:
        assert len(field.label) <= PIPELINE_INPUT_LABEL_MAX_LENGTH
        assert len(field.description) <= PIPELINE_INPUT_DESCRIPTION_MAX_LENGTH
    for step in template.steps:
        assert len(step.title) <= STEP_TITLE_MAX_LENGTH
        assert len(step.role) <= STEP_ROLE_MAX_LENGTH
        assert len(step.expected_output) <= STEP_EXPECTED_OUTPUT_MAX_LENGTH


@each_template
def test_prompts_use_every_declared_input_and_nothing_else(template: MissionTemplate) -> None:
    declared = {field.name for field in template.inputs}
    used = set().union(*(placeholders(step.prompt) for step in template.steps))
    assert used == declared | {RESERVED_INPUT_NAME}


@each_template
def test_each_stage_places_its_input(template: MissionTemplate) -> None:
    for step in template.steps:
        if step.stage == 1:
            # The first stage's input is the named inputs: it places them itself.
            assert STAGE_INPUT not in step.prompt and placeholders(step.prompt), step.title
        else:
            assert step.prompt.count(STAGE_INPUT) == 1, step.title


@each_template
def test_stages_fan_out_then_end_with_a_lone_reviewer(template: MissionTemplate) -> None:
    stages = [step.stage for step in template.steps]
    assert stages == sorted(stages)
    assert sorted(set(stages)) == list(range(1, stages[-1] + 1))
    assert stages.count(1) >= 2, "independent research runs in parallel"
    *work, reviewer = template.steps
    assert stages.count(reviewer.stage) == 1
    assert reviewer.is_output and reviewer.role == REVIEWER_ROLE
    assert not any(step.is_output for step in work)


@each_template
def test_templates_grant_only_named_built_in_tools(template: MissionTemplate) -> None:
    for step in template.steps:
        assert step.tools is not None, "explicit tool lists keep agents least-privileged"
        assert set(step.tools) <= set(TOOLBOX), step.title
        assert len(set(step.tools)) == len(step.tools)


def test_an_unknown_slug_is_not_found_before_any_tool_discovery(
    session: Session, user: User
) -> None:
    discoveries: list[int] = []

    def discover() -> list[ToolDescriptor]:
        discoveries.append(1)
        return []

    with pytest.raises(NotFound):
        use_template(session, user, TemplateChoice("no-such"), StepDefaults(["m"], discover))
    assert discoveries == []


# --- GET /templates -------------------------------------------------------------


def test_the_gallery_lists_every_template_with_its_inputs_and_size(
    auth_client: TestClient,
) -> None:
    response = auth_client.get("/api/templates")

    assert response.status_code == 200
    body = response.json()
    assert [item["slug"] for item in body] == [template.slug for template in CATALOGUE]
    template = CATALOGUE[0]
    assert body[0] == {
        "slug": template.slug,
        "title": template.title,
        "category": template.category,
        "description": template.description,
        "inputs": [asdict(field) for field in template.inputs],
        "step_count": len(template.steps),
        "stage_count": len({step.stage for step in template.steps}),
    }


# --- POST /templates/<slug>/use -------------------------------------------------


def test_using_a_template_creates_the_callers_pipeline_on_their_default_model(
    auth_client: TestClient, user: User, session: Session, default_model: str
) -> None:
    template = get_template("market-research-brief")

    response = auth_client.post(f"/api/templates/{template.slug}/use")

    assert response.status_code == 201
    body = response.json()
    assert (body["user"], body["name"]) == (user.id, template.title)
    assert body["inputs"] == [asdict(field) for field in template.inputs]
    assert [step["order"] for step in body["steps"]] == [1, 2, 3, 4, 5]
    assert [step["stage"] for step in body["steps"]] == [step.stage for step in template.steps]
    assert [step["prompt"] for step in body["steps"]] == [s.prompt for s in template.steps]
    assert [step["is_output"] for step in body["steps"]] == [False, False, False, False, True]
    assert {step["model"] for step in body["steps"]} == {default_model}
    stored = session.get(Pipeline, body["id"])
    assert stored is not None and stored.user_id == user.id


def test_steps_get_the_users_own_default_model(app: FastAPI, auth_client: TestClient) -> None:
    chosen = available_model_ids("openrouter")[1]
    app.dependency_overrides[llm_profile] = lambda: LLMProfile("openrouter", chosen)

    response = auth_client.post("/api/templates/content-calendar/use", json={})

    assert {step["model"] for step in response.json()["steps"]} == {chosen}


def test_tools_the_user_lacks_are_dropped(auth_client: TestClient) -> None:
    # The test settings offer fetch_url, calculator and current_datetime, but
    # no web_search: it needs a search key.
    response = auth_client.post("/api/templates/market-research-brief/use")

    assert step_tools(response.json()) == [
        ["fetch_url", "current_datetime", "calculator"],
        ["fetch_url"],
        ["fetch_url", "current_datetime"],
        [],
        [],
    ]


def test_tools_the_user_has_are_kept(app: FastAPI, auth_client: TestClient) -> None:
    use_tools(app, ["web_search", "fetch_url", "read_csv", "list_workspace_files"])

    research = auth_client.post("/api/templates/competitor-analysis/use").json()
    data = auth_client.post("/api/templates/data-insights-report/use").json()

    web = ["web_search", "fetch_url"]
    assert step_tools(research) == [web, web, [], []]
    assert step_tools(data)[:2] == [["list_workspace_files", "read_csv"]] * 2


def test_a_template_can_be_used_under_another_name(auth_client: TestClient) -> None:
    response = auth_client.post("/api/templates/document-digest/use", json={"name": " Lease "})

    assert response.status_code == 201
    assert response.json()["name"] == "Lease"


def test_a_blank_name_is_a_validation_error(auth_client: TestClient) -> None:
    response = auth_client.post("/api/templates/document-digest/use", json={"name": "  "})

    assert response.status_code == 400
    assert response.json()["error"] == "validation_error"
    assert auth_client.get("/api/pipelines/").json() == []


def test_an_unknown_template_is_a_404_that_creates_nothing(auth_client: TestClient) -> None:
    response = auth_client.post("/api/templates/no-such-template/use")

    assert response.status_code == 404
    assert response.json() == {
        "error": "not_found",
        "detail": "Template 'no-such-template' was not found.",
    }
    assert auth_client.get("/api/pipelines/").json() == []


def test_a_template_pipeline_belongs_only_to_its_creator(
    auth_client: TestClient, session: Session
) -> None:
    created = auth_client.post("/api/templates/meeting-actions/use").json()
    stranger = bearer(users.create(session, "stranger", hash_password("x-pass-2891", 1)))

    assert [row["id"] for row in auth_client.get("/api/pipelines/").json()] == [created["id"]]
    assert auth_client.get("/api/pipelines/", headers=stranger).json() == []
    path = f"/api/pipelines/{created['id']}/"
    assert auth_client.get(path, headers=stranger).status_code == 404


def test_a_template_pipeline_runs_on_its_named_inputs(
    auth_client: TestClient, fake_provider: FakeProvider
) -> None:
    created = auth_client.post("/api/templates/document-digest/use").json()
    inputs = {"document": "The lease ends on 1 May.", "reader": "the tenant"}

    response = auth_client.post(f"/api/pipelines/{created['id']}/run", json={"inputs": inputs})

    assert response.status_code == 200
    results = response.json()["intermediate_results"]
    assert [result["is_output"] for result in results] == [False, False, False, False, True]
    reviewer_prompt = fake_provider.calls[-1][0]
    # The reviewer checks the draft against the original document and the brief.
    assert "The lease ends on 1 May." in reviewer_prompt
    assert "Their request:\nWho it is for: the tenant" in reviewer_prompt
    assert reviewer_prompt.endswith("Draft:\nfake reply")
