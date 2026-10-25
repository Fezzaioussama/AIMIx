"""The routes that make the server spend: each is rate limited per account, and
what they are sent is bounded, so one request cannot carry an unbounded prompt."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.deps import app_settings, user_rate_limit
from api.models import PIPELINE_MAX_INPUTS, User
from api.routes import API_PREFIX, PROTECTED_ROUTERS
from api.schemas.chat import CHAT_PROMPT_MAX_LENGTH
from api.schemas.common import PIPELINE_MAX_STEPS, RUN_INPUT_MAX_LENGTH, STEP_PROMPT_MAX_LENGTH
from api.schemas.planning import PLAN_DESCRIPTION_MAX_LENGTH
from tests.conftest import TEST_SETTINGS, FakeAgent, FakeProvider, use_agent
from tests.test_endpoints import make_pipeline

#: Every route that calls a model, starts a run or builds a pipeline from a template.
SPENDING_ROUTES = {
    ("POST", "/api/pipelines/{pipeline_id}/runs"),
    ("POST", "/api/pipelines/{pipeline_id}/run"),
    ("POST", "/api/runs/{run_id}/resume"),
    ("POST", "/api/schedules/{schedule_id}/run"),
    ("POST", "/api/pipelines/generate"),
    ("POST", "/api/pipelines/revise"),
    ("POST", "/api/chat"),
    ("POST", "/api/templates/{slug}/use"),
}


def rate_limited_routes() -> set[tuple[str, str]]:
    """Every (method, path) whose route depends on ``user_rate_limit``."""
    return {
        (method, f"{API_PREFIX}{route.path}")
        for router in PROTECTED_ROUTERS
        for route in router.routes
        if isinstance(route, APIRoute)
        and any(dep.dependency is user_rate_limit for dep in route.dependencies)
        for method in route.methods
    }


def test_every_route_that_spends_is_rate_limited_per_account() -> None:
    assert rate_limited_routes() >= SPENDING_ROUTES


def test_chat_is_refused_once_an_account_used_up_its_requests(
    app: FastAPI, auth_client: TestClient
) -> None:
    app.dependency_overrides[app_settings] = lambda: TEST_SETTINGS.model_copy(
        update={"user_rate_limit_requests": 1}
    )
    use_agent(app, FakeAgent())

    assert auth_client.post("/api/chat", json={"prompt": "hi"}).status_code == 200
    refused = auth_client.post("/api/chat", json={"prompt": "hi again"})

    assert (refused.status_code, refused.json()["error"]) == (429, "throttled")


# --- bounded bodies ---------------------------------------------------------------------


def step(prompt: str, order: int = 1) -> dict[str, Any]:
    return {"order": order, "prompt": prompt, "model": TEST_SETTINGS.openrouter_default_model}


def refused(response: Any, fragment: str) -> None:
    assert response.status_code == 400, response.text
    assert response.json()["error"] == "validation_error"
    assert fragment in response.json()["detail"]


def test_a_chat_message_has_a_maximum_length(app: FastAPI, auth_client: TestClient) -> None:
    use_agent(app, FakeAgent())
    longest = "x" * CHAT_PROMPT_MAX_LENGTH

    assert auth_client.post("/api/chat", json={"prompt": longest}).status_code == 200
    refused(auth_client.post("/api/chat", json={"prompt": longest + "x"}), "prompt")


def test_a_pipeline_has_bounded_steps_and_prompts(auth_client: TestClient) -> None:
    long_prompt = {"name": "Long", "steps": [step("x" * (STEP_PROMPT_MAX_LENGTH + 1))]}
    refused(auth_client.post("/api/pipelines/", json=long_prompt), "steps.0.prompt")

    many = [step("go", order) for order in range(1, PIPELINE_MAX_STEPS + 2)]
    refused(auth_client.post("/api/pipelines/", json={"name": "Many", "steps": many}), "steps")

    most = [step("go", order) for order in range(1, PIPELINE_MAX_STEPS + 1)]
    assert (
        auth_client.post("/api/pipelines/", json={"name": "Most", "steps": most}).status_code == 201
    )


def test_the_planner_is_sent_bounded_text(
    auth_client: TestClient, fake_provider: FakeProvider
) -> None:
    mission = {"description": "x" * (PLAN_DESCRIPTION_MAX_LENGTH + 1)}
    refused(auth_client.post("/api/pipelines/generate", json=mission), "description")

    draft = {"name": "Draft", "steps": [step("x" * (STEP_PROMPT_MAX_LENGTH + 1))]}
    revise = {"pipeline": draft, "instruction": "Shorter"}
    refused(auth_client.post("/api/pipelines/revise", json=revise), "prompt")
    assert fake_provider.calls == []


@pytest.mark.parametrize(
    "body",
    [
        {"input": "x" * (RUN_INPUT_MAX_LENGTH + 1)},
        {"inputs": {"a": "x" * RUN_INPUT_MAX_LENGTH, "b": "x"}},
    ],
)
def test_what_a_run_is_given_is_bounded_in_all(
    auth_client: TestClient, session: Session, user: User, body: dict[str, Any]
) -> None:
    pipeline = make_pipeline(session, user, "Big")

    refused(
        auth_client.post(f"/api/pipelines/{pipeline.id}/runs", json=body),
        f"at most {RUN_INPUT_MAX_LENGTH:,} characters",
    )


def test_a_run_names_at_most_as_many_inputs_as_a_pipeline_declares(
    auth_client: TestClient, session: Session, user: User
) -> None:
    pipeline = make_pipeline(session, user, "Named")
    values = {f"input_{n}": "v" for n in range(PIPELINE_MAX_INPUTS + 1)}

    refused(
        auth_client.post(f"/api/pipelines/{pipeline.id}/runs", json={"inputs": values}), "inputs"
    )


def test_a_document_sized_input_still_fits(
    auth_client: TestClient, session: Session, user: User, fake_provider: FakeProvider
) -> None:
    pipeline = make_pipeline(session, user, "Doc")
    document = "word " * (TEST_SETTINGS.document_max_chars // 5)

    response = auth_client.post(f"/api/pipelines/{pipeline.id}/runs", json={"input": document})

    assert response.status_code == 202, response.text
