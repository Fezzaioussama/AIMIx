"""The error contract: every failure answers {"error": <code>, "detail": <msg>}."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.deps import provider_factory
from api.errors import error_body
from api.exceptions import NotFound, ProviderTimedOut


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


def test_unauthenticated_request_uses_the_error_shape(client: TestClient) -> None:
    response = client.get("/api/models")
    assert response.status_code == 401
    assert_error_shape(response.json())
    assert response.json()["error"] == "not_authenticated"


def test_validation_failure_uses_the_error_shape(auth_client: TestClient) -> None:
    response = auth_client.post("/api/chat", json={})
    assert response.status_code == 400
    assert_error_shape(response.json())
    assert response.json() == {"error": "validation_error", "detail": "prompt: Field required"}


def test_malformed_json_is_a_validation_error(auth_client: TestClient) -> None:
    response = auth_client.post(
        "/api/chat", content=b"{not json", headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 400
    assert_error_shape(response.json())


def test_missing_pipeline_uses_the_error_shape(auth_client: TestClient) -> None:
    response = auth_client.post("/api/pipelines/999/run", json={"input": "hi"})
    assert response.status_code == 404
    assert_error_shape(response.json())
    assert response.json()["error"] == "not_found"


def test_unknown_route_uses_the_error_shape(client: TestClient) -> None:
    response = client.get("/api/nowhere")
    assert response.status_code == 404
    assert_error_shape(response.json())


def test_method_not_allowed_uses_the_error_shape(auth_client: TestClient) -> None:
    response = auth_client.delete("/api/models")
    assert response.status_code == 405
    assert_error_shape(response.json())
    assert response.json()["error"] == "method_not_allowed"


def test_an_unexpected_failure_is_a_500_in_the_error_shape(
    app: FastAPI, auth_client: TestClient
) -> None:
    def broken() -> None:
        raise RuntimeError("boom")

    app.dependency_overrides[provider_factory] = broken
    with TestClient(app, raise_server_exceptions=False) as client:
        client.headers.update(auth_client.headers)
        response = client.post("/api/chat", json={"prompt": "hi"})
    assert response.status_code == 500
    assert response.json() == {"error": "server_error", "detail": "An unexpected error occurred."}
