"""HTTP surface: auth enforcement, ownership, and response shapes."""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.models import Pipeline, PipelineStep, User
from api.repositories import users
from api.security import hash_password
from llm import exceptions as llm_exceptions
from tests.conftest import FailingProvider, FakeProvider, bearer, use_provider

PUBLIC_PATHS = {"/api/register", "/api/login", "/api/token/refresh"}


def make_pipeline(session: Session, owner: User, name: str, model: str, steps: int = 1) -> Pipeline:
    pipeline = Pipeline(
        user=owner,
        name=name,
        steps=[
            PipelineStep(
                order=n, stage=n, title="", is_output=False, prompt=f"s{n} {{input}}", model=model
            )
            for n in range(1, steps + 1)
        ],
    )
    session.add(pipeline)
    session.commit()
    return pipeline


def feature_routes(app: FastAPI) -> list[tuple[str, str]]:
    """Every (method, path) the API serves outside the public allowlist."""
    return [
        (method.upper(), path.replace("{pipeline_id}", "1"))
        for path, operations in app.openapi()["paths"].items()
        if path not in PUBLIC_PATHS
        for method in operations
    ]


def test_every_non_public_route_requires_authentication(app: FastAPI, client: TestClient) -> None:
    routes = feature_routes(app)
    assert len(routes) >= 10
    for method, path in routes:
        response = client.request(method, path)
        assert response.status_code == 401, (method, path)
        assert response.headers["www-authenticate"] == "Bearer"


def test_an_invalid_token_is_rejected(client: TestClient) -> None:
    response = client.get("/api/models", headers={"Authorization": "Bearer not-a-jwt"})
    assert response.status_code == 401
    assert response.json()["error"] == "not_authenticated"


def test_register_is_public_and_creates_a_user(client: TestClient, session: Session) -> None:
    response = client.post(
        "/api/register", json={"username": "newcomer", "password": "a-strong-pass-9182"}
    )
    assert response.status_code == 201
    assert response.json() == {"username": "newcomer"}
    assert users.get_by_username(session, "newcomer") is not None


def test_register_rejects_a_weak_password(client: TestClient) -> None:
    response = client.post("/api/register", json={"username": "weak", "password": "123"})
    assert response.status_code == 400
    assert set(response.json()) == {"error", "detail"}
    assert "too short" in response.json()["detail"]


def test_register_rejects_a_taken_username(client: TestClient, user: User) -> None:
    response = client.post(
        "/api/register", json={"username": user.username, "password": "a-strong-pass-9182"}
    )
    assert response.status_code == 400
    assert "already exists" in response.json()["detail"]


def test_login_returns_a_token_pair_that_can_be_refreshed(
    client: TestClient, user: User, password: str
) -> None:
    login = client.post("/api/login", json={"username": user.username, "password": password})
    assert login.status_code == 200
    tokens = login.json()
    assert set(tokens) == {"access", "refresh"}

    refreshed = client.post("/api/token/refresh", json={"refresh": tokens["refresh"]})
    assert refreshed.status_code == 200
    access = refreshed.json()["access"]
    who = client.get("/api/protected", headers={"Authorization": f"Bearer {access}"})
    assert who.json()["user_id"] == user.id


def test_login_rejects_a_wrong_password(client: TestClient, user: User) -> None:
    response = client.post("/api/login", json={"username": user.username, "password": "nope"})
    assert response.status_code == 401
    assert response.json()["error"] == "not_authenticated"


def test_a_refresh_token_is_not_an_access_token(
    client: TestClient, user: User, password: str
) -> None:
    refresh = client.post(
        "/api/login", json={"username": user.username, "password": password}
    ).json()["refresh"]
    response = client.get("/api/models", headers={"Authorization": f"Bearer {refresh}"})
    assert response.status_code == 401


def test_models_endpoint_serves_the_catalogue(auth_client: TestClient, default_model: str) -> None:
    response = auth_client.get("/api/models")
    assert response.status_code == 200
    body = response.json()
    assert body["default"] == default_model
    assert body["models"][0] == default_model
    assert len(body["models"]) > 1


def test_creating_a_pipeline_assigns_the_caller_as_owner(
    auth_client: TestClient, user: User, session: Session, default_model: str
) -> None:
    response = auth_client.post(
        "/api/pipelines/",
        json={"name": "Mine", "steps": [{"order": 1, "prompt": "x", "model": default_model}]},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["user"] == user.id
    assert body["steps"][0]["stage"] == 1
    assert body["created_at"].endswith("Z") or body["created_at"].endswith("+00:00")
    stored = session.get(Pipeline, body["id"])
    assert stored is not None and stored.user_id == user.id


def test_a_pipeline_can_be_read_replaced_patched_and_deleted(
    auth_client: TestClient, user: User, session: Session, default_model: str
) -> None:
    pipeline = make_pipeline(session, user, "Draft", default_model, steps=2)
    path = f"/api/pipelines/{pipeline.id}/"

    assert auth_client.get(path).json()["name"] == "Draft"

    replaced = auth_client.put(
        path,
        json={"name": "Final", "steps": [{"order": 1, "prompt": "only", "model": default_model}]},
    )
    assert replaced.status_code == 200
    assert [s["prompt"] for s in replaced.json()["steps"]] == ["only"]

    renamed = auth_client.patch(path, json={"name": "Renamed"})
    assert renamed.json()["name"] == "Renamed"
    assert len(renamed.json()["steps"]) == 1

    assert auth_client.delete(path).status_code == 204
    assert auth_client.get(path).status_code == 404


def test_replacing_steps_can_reuse_their_orders(
    auth_client: TestClient, user: User, session: Session, default_model: str
) -> None:
    pipeline = make_pipeline(session, user, "Reorder", default_model, steps=2)
    steps = [
        {"order": 2, "prompt": "b", "model": default_model},
        {"order": 1, "prompt": "a", "model": default_model},
    ]
    response = auth_client.put(f"/api/pipelines/{pipeline.id}/", json={"name": "R", "steps": steps})
    assert response.status_code == 200
    assert [s["order"] for s in response.json()["steps"]] == [1, 2]


def test_duplicate_step_orders_are_a_validation_error(
    auth_client: TestClient, default_model: str
) -> None:
    step = {"order": 1, "prompt": "x", "model": default_model}
    response = auth_client.post("/api/pipelines/", json={"name": "Dup", "steps": [step, step]})
    assert response.status_code == 400
    assert "unique order" in response.json()["detail"]


def test_pipelines_are_scoped_to_their_owner(
    auth_client: TestClient, session: Session, default_model: str
) -> None:
    stranger = users.create(session, "stranger", hash_password("x-pass-2891", 1))
    theirs = make_pipeline(session, stranger, "Theirs", default_model)

    assert auth_client.get("/api/pipelines/").json() == []

    denied = auth_client.post(f"/api/pipelines/{theirs.id}/run", json={"input": "go"})
    # Someone else's pipeline is indistinguishable from a missing one.
    assert denied.status_code == 404
    assert denied.json()["error"] == "not_found"
    assert auth_client.delete(f"/api/pipelines/{theirs.id}/").status_code == 404


def test_the_list_is_newest_first(
    auth_client: TestClient, user: User, session: Session, default_model: str
) -> None:
    make_pipeline(session, user, "Older", default_model)
    make_pipeline(session, user, "Newer", default_model)
    names = [row["name"] for row in auth_client.get("/api/pipelines/").json()]
    assert names == ["Newer", "Older"]


def test_running_a_pipeline_returns_every_step(
    auth_client: TestClient, user: User, session: Session, fake_provider, default_model: str
) -> None:
    pipeline = make_pipeline(session, user, "Runner", default_model, steps=2)

    response = auth_client.post(f"/api/pipelines/{pipeline.id}/run", json={"input": "seed"})

    assert response.status_code == 200
    body = response.json()
    assert body["pipeline_name"] == "Runner"
    assert [step["stage"] for step in body["intermediate_results"]] == [1, 2]
    # No step is marked, so the last stage is the pipeline's output.
    assert [step["is_output"] for step in body["intermediate_results"]] == [False, True]
    assert body["final_output"] == "fake reply"


def test_running_a_stepless_pipeline_is_a_validation_error(
    auth_client: TestClient, user: User, session: Session, fake_provider
) -> None:
    pipeline = Pipeline(user=user, name="Empty")
    session.add(pipeline)
    session.commit()
    response = auth_client.post(f"/api/pipelines/{pipeline.id}/run", json={"input": "seed"})
    assert response.status_code == 400
    assert response.json()["error"] == "validation_error"


def test_provider_timeout_surfaces_as_504(
    app: FastAPI, auth_client: TestClient, user: User, session: Session, default_model: str
) -> None:
    pipeline = make_pipeline(session, user, "Slow", default_model)
    use_provider(app, FailingProvider(llm_exceptions.ProviderTimeout("slow")))

    response = auth_client.post(f"/api/pipelines/{pipeline.id}/run", json={"input": "go"})
    assert response.status_code == 504
    assert response.json()["error"] == "provider_timeout"


def test_generate_returns_a_plan_and_the_catalogue(
    app: FastAPI, auth_client: TestClient, default_model: str
) -> None:
    plan = json.dumps(
        {"name": "Generated", "steps": [{"order": 1, "prompt": "p", "model": default_model}]}
    )
    use_provider(app, FakeProvider(reply=plan))

    response = auth_client.post("/api/pipelines/generate", json={"description": "do a thing"})

    assert response.status_code == 200
    body = response.json()
    assert body["generated_pipeline"]["name"] == "Generated"
    assert body["available_models"][0] == default_model


def test_chat_streams_the_reply(auth_client: TestClient, fake_provider) -> None:
    response = auth_client.post("/api/chat", json={"prompt": "hello"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert response.text == "fake reply"


def test_chat_reports_an_unconfigured_provider_before_streaming(auth_client: TestClient) -> None:
    # The test settings leave every provider key empty.
    response = auth_client.post("/api/chat", json={"prompt": "hello"})
    assert response.status_code == 503
    assert response.json()["error"] == "provider_not_configured"


def test_a_signed_in_user_is_greeted(client: TestClient, user: User) -> None:
    response = client.get("/api/protected", headers=bearer(user))
    assert response.json() == {
        "message": "Hello tester, your token is valid.",
        "user_id": user.id,
    }


@pytest.mark.parametrize("path", ["/api/docs", "/api/openapi.json"])
def test_interactive_docs_are_served_outside_production(client: TestClient, path: str) -> None:
    assert client.get(path).status_code == 200
