"""The error contract: every failure answers {"error": <code>, "detail": <msg>}."""

from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from api.errors import error_body
from api.exceptions import NotFound, ProviderTimedOut

pytestmark = pytest.mark.django_db


def assert_error_shape(payload: object) -> None:
    assert isinstance(payload, dict), payload
    assert set(payload) == {"error", "detail"}, payload
    assert isinstance(payload["error"], str) and payload["error"]
    assert isinstance(payload["detail"], str) and payload["detail"]


def test_error_body_is_the_documented_shape() -> None:
    assert error_body("not_found", "gone") == {"error": "not_found", "detail": "gone"}


def test_domain_errors_carry_their_code_and_status() -> None:
    assert NotFound("x").status_code == 404
    assert NotFound("x").code == "not_found"
    assert ProviderTimedOut("x").status_code == 504
    assert ProviderTimedOut("x").code == "provider_timeout"


def test_unauthenticated_request_uses_the_error_shape(client: APIClient) -> None:
    response = client.get(reverse("list_models"))
    assert response.status_code == 401
    assert_error_shape(response.json())
    assert response.json()["error"] == "not_authenticated"


def test_validation_failure_uses_the_error_shape(auth_client: APIClient) -> None:
    response = auth_client.post(reverse("chat_view"), {}, format="json")
    assert response.status_code == 400
    assert_error_shape(response.json())
    assert response.json()["error"] == "validation_error"


def test_missing_pipeline_uses_the_error_shape(auth_client: APIClient) -> None:
    response = auth_client.post(reverse("run_pipeline", args=[999]), {"input": "hi"}, format="json")
    assert response.status_code == 404
    assert_error_shape(response.json())
    assert response.json()["error"] == "not_found"


def test_method_not_allowed_uses_the_error_shape(auth_client: APIClient) -> None:
    response = auth_client.delete(reverse("list_models"))
    assert response.status_code == 405
    assert_error_shape(response.json())
