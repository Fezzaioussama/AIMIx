"""HTTP surface: auth enforcement, ownership, and response shapes."""

from __future__ import annotations

import json

import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework.test import APIClient

from api.models import Pipeline, PipelineStep
from llm import exceptions as llm_exceptions
from tests.conftest import FailingProvider

pytestmark = pytest.mark.django_db

PROTECTED_ROUTES = [
    ("get", "list_models", []),
    ("get", "protected_view", []),
    ("post", "chat_view", []),
    ("get", "pipeline-list", []),
    ("post", "generate_pipeline", []),
    ("post", "run_pipeline", [1]),
]


@pytest.mark.parametrize(("method", "route", "args"), PROTECTED_ROUTES)
def test_every_feature_route_requires_authentication(
    client: APIClient, method: str, route: str, args: list
) -> None:
    response = getattr(client, method)(reverse(route, args=args))
    assert response.status_code == 401, route


def test_register_is_public_and_creates_a_user(client: APIClient) -> None:
    response = client.post(
        reverse("auth_register"),
        {"username": "newcomer", "password": "a-strong-pass-9182"},
        format="json",
    )
    assert response.status_code == 201
    assert User.objects.filter(username="newcomer").exists()


def test_register_rejects_a_weak_password(client: APIClient) -> None:
    response = client.post(
        reverse("auth_register"), {"username": "weak", "password": "123"}, format="json"
    )
    assert response.status_code == 400
    assert set(response.json()) == {"error", "detail"}


def test_login_returns_a_token_pair(client: APIClient, user: User, password: str) -> None:
    response = client.post(
        reverse("token_obtain_pair"),
        {"username": user.username, "password": password},
        format="json",
    )
    assert response.status_code == 200
    assert {"access", "refresh"} <= set(response.json())


def test_models_endpoint_serves_the_catalogue(auth_client: APIClient, default_model: str) -> None:
    response = auth_client.get(reverse("list_models"))
    assert response.status_code == 200
    body = response.json()
    assert body["default"] == default_model
    assert body["models"][0] == default_model
    assert len(body["models"]) > 1


def test_creating_a_pipeline_assigns_the_caller_as_owner(
    auth_client: APIClient, user: User, default_model: str
) -> None:
    response = auth_client.post(
        reverse("pipeline-list"),
        {"name": "Mine", "steps": [{"order": 1, "prompt": "x", "model": default_model}]},
        format="json",
    )
    assert response.status_code == 201
    assert Pipeline.objects.get(pk=response.json()["id"]).user == user


def test_pipelines_are_scoped_to_their_owner(auth_client: APIClient, default_model: str) -> None:
    stranger = User.objects.create_user(username="stranger", password="x-pass-2891")
    theirs = Pipeline.objects.create(user=stranger, name="Theirs")
    PipelineStep.objects.create(pipeline=theirs, order=1, prompt="p", model=default_model)

    listed = auth_client.get(reverse("pipeline-list")).json()
    assert [row["name"] for row in listed] == []

    denied = auth_client.post(
        reverse("run_pipeline", args=[theirs.pk]), {"input": "go"}, format="json"
    )
    # Someone else's pipeline is indistinguishable from a missing one.
    assert denied.status_code == 404
    assert denied.json()["error"] == "not_found"


def test_running_a_pipeline_returns_every_step(
    auth_client: APIClient, user: User, fake_provider, default_model: str
) -> None:
    pipeline = Pipeline.objects.create(user=user, name="Runner")
    PipelineStep.objects.create(pipeline=pipeline, order=1, prompt="a {input}", model=default_model)
    PipelineStep.objects.create(pipeline=pipeline, order=2, prompt="b {input}", model=default_model)

    response = auth_client.post(
        reverse("run_pipeline", args=[pipeline.pk]), {"input": "seed"}, format="json"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["pipeline_name"] == "Runner"
    assert len(body["intermediate_results"]) == 2
    assert body["final_output"] == "fake reply"


def test_running_a_stepless_pipeline_is_a_validation_error(
    auth_client: APIClient, user: User, fake_provider
) -> None:
    pipeline = Pipeline.objects.create(user=user, name="Empty")
    response = auth_client.post(
        reverse("run_pipeline", args=[pipeline.pk]), {"input": "seed"}, format="json"
    )
    assert response.status_code == 400
    assert response.json()["error"] == "validation_error"


def test_provider_timeout_surfaces_as_504(
    auth_client: APIClient, user: User, monkeypatch: pytest.MonkeyPatch, default_model: str
) -> None:
    pipeline = Pipeline.objects.create(user=user, name="Slow")
    PipelineStep.objects.create(pipeline=pipeline, order=1, prompt="p", model=default_model)
    monkeypatch.setattr(
        "api.endpoints.pipelines.get_provider",
        lambda: FailingProvider(llm_exceptions.ProviderTimeout("slow")),
    )

    response = auth_client.post(
        reverse("run_pipeline", args=[pipeline.pk]), {"input": "go"}, format="json"
    )
    assert response.status_code == 504
    assert response.json()["error"] == "provider_timeout"


def test_generate_returns_a_plan_and_the_catalogue(
    auth_client: APIClient, monkeypatch: pytest.MonkeyPatch, default_model: str
) -> None:
    from tests.conftest import FakeProvider

    plan = json.dumps(
        {"name": "Generated", "steps": [{"order": 1, "prompt": "p", "model": default_model}]}
    )
    monkeypatch.setattr("api.endpoints.pipelines.get_provider", lambda: FakeProvider(reply=plan))

    response = auth_client.post(
        reverse("generate_pipeline"), {"description": "do a thing"}, format="json"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["generated_pipeline"]["name"] == "Generated"
    assert body["available_models"][0] == default_model


def test_chat_streams_the_reply(auth_client: APIClient, fake_provider) -> None:
    response = auth_client.post(reverse("chat_view"), {"prompt": "hello"}, format="json")
    assert response.status_code == 200
    assert b"".join(response.streaming_content) == b"fake reply"


def test_chat_reports_an_unconfigured_provider_before_streaming(
    auth_client: APIClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from api.exceptions import ProviderNotConfigured

    def unconfigured():
        raise ProviderNotConfigured("OPEN_ROUTER_KEY is not set.")

    monkeypatch.setattr("api.endpoints.chat.get_provider", unconfigured)

    response = auth_client.post(reverse("chat_view"), {"prompt": "hello"}, format="json")
    assert response.status_code == 503
    assert response.json()["error"] == "provider_not_configured"
