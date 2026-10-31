"""The Settings page: per-user provider, encrypted API keys and default models."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.deps import secret_box
from api.models import ProviderSetting, User
from api.repositories import users
from api.security import SecretBox, hash_password
from api.services import llm as llm_service
from api.services import llm_settings
from config.settings import pin_settings
from llm.base import ProviderConfig
from tests.conftest import TEST_SETTINGS, FakeProvider, bearer

SETTINGS_URL = "/api/llm-settings"
OPENROUTER_KEY = "sk-or-v1-test-key-9876"
#: A catalogued OpenRouter model that is not the configured default.
CHOSEN_MODEL = "x-ai/grok-4.20"
TOGETHER_MODEL = "moonshotai/Kimi-K2-Thinking"


def openrouter(**fields: Any) -> dict[str, Any]:
    return {"name": "openrouter", "default_model": CHOSEN_MODEL, **fields}


def save(client: TestClient, provider: str = "openrouter", **fields: Any) -> Any:
    body = {"provider": provider, "providers": [openrouter(**fields)]}
    return client.put(SETTINGS_URL, json=body)


def provider_entry(body: dict[str, Any], name: str) -> dict[str, Any]:
    return next(entry for entry in body["providers"] if entry["name"] == name)


def pinned_environment(**update: Any) -> Iterator[None]:
    pin_settings(TEST_SETTINGS.model_copy(update={"openrouter_api_key": "env-key", **update}))
    yield
    pin_settings(TEST_SETTINGS)


@pytest.fixture
def environment_key() -> Iterator[None]:
    """An OpenRouter key in backend/.env that accounts may NOT use (the default)."""
    yield from pinned_environment()


@pytest.fixture
def shared_environment_key() -> Iterator[None]:
    """The same key, with the operator opting in to sharing it (ALLOW_SERVER_LLM_KEY)."""
    yield from pinned_environment(allow_server_llm_key=True)


def test_a_new_user_sees_the_environment_defaults(
    auth_client: TestClient, default_model: str
) -> None:
    body = auth_client.get(SETTINGS_URL).json()
    assert body["provider"] == "openrouter"
    assert [entry["name"] for entry in body["providers"]] == ["meta", "openrouter", "togetherai"]
    entry = provider_entry(body, "openrouter")
    assert (entry["key_source"], entry["key_hint"]) == ("none", "")
    assert entry["default_model"] == default_model
    assert entry["models"][0] == default_model


@pytest.mark.usefixtures("shared_environment_key")
def test_a_shared_key_in_the_environment_is_reported_without_being_revealed(
    auth_client: TestClient,
) -> None:
    response = auth_client.get(SETTINGS_URL)
    assert provider_entry(response.json(), "openrouter")["key_source"] == "environment"
    assert "env-key" not in response.text


def test_a_saved_key_is_encrypted_and_never_returned(
    auth_client: TestClient, session: Session, user: User
) -> None:
    response = save(auth_client, api_key=f"  {OPENROUTER_KEY}  ")

    assert response.status_code == 200
    assert OPENROUTER_KEY not in response.text
    entry = provider_entry(response.json(), "openrouter")
    assert (entry["key_source"], entry["key_hint"]) == ("saved", "9876")
    assert entry["default_model"] == CHOSEN_MODEL
    row = session.query(ProviderSetting).filter_by(user_id=user.id).one()
    assert OPENROUTER_KEY not in row.api_key_encrypted
    assert SecretBox(TEST_SETTINGS.secret_key).open(row.api_key_encrypted) == OPENROUTER_KEY


def test_saving_without_a_key_keeps_the_saved_one(auth_client: TestClient) -> None:
    save(auth_client, api_key=OPENROUTER_KEY)
    first = auth_client.get(SETTINGS_URL).json()

    response = save(auth_client)

    assert response.status_code == 200
    assert response.json() == first


def test_the_active_provider_and_its_default_drive_the_model_catalogue(
    auth_client: TestClient,
) -> None:
    body = {
        "provider": "togetherai",
        "providers": [{"name": "togetherai", "default_model": TOGETHER_MODEL}],
    }
    assert auth_client.put(SETTINGS_URL, json=body).status_code == 200

    models = auth_client.get("/api/models").json()
    assert models["default"] == TOGETHER_MODEL
    assert models["models"][0] == TOGETHER_MODEL
    assert CHOSEN_MODEL not in models["models"]


def test_the_saved_key_and_model_reach_the_provider(
    auth_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    built: list[ProviderConfig] = []
    plan = json.dumps({"name": "P", "steps": [{"order": 1, "prompt": "p", "model": "m"}]})
    provider = FakeProvider(reply=plan)

    def capture(name: str, config: ProviderConfig) -> FakeProvider:
        built.append(config)
        return provider

    monkeypatch.setattr(llm_service, "create_provider", capture)
    save(auth_client, api_key=OPENROUTER_KEY)

    response = auth_client.post("/api/pipelines/generate", json={"description": "a thing"})

    assert response.status_code == 200
    assert [(config.api_key, config.default_model) for config in built] == [
        (OPENROUTER_KEY, CHOSEN_MODEL)
    ]
    # No planner chosen: the user's default plans, and fills in unknown step models.
    assert provider.calls[0][1] == CHOSEN_MODEL
    assert response.json()["generated_pipeline"]["steps"][0]["model"] == CHOSEN_MODEL


def test_settings_are_private_to_each_user(
    client: TestClient, session: Session, user: User
) -> None:
    client.put(
        SETTINGS_URL,
        json={"provider": "togetherai", "providers": [openrouter(api_key=OPENROUTER_KEY)]},
        headers=bearer(user),
    )
    other = users.create(session, "someone-else", hash_password("other-pass-123", 1))

    body = client.get(SETTINGS_URL, headers=bearer(other)).json()

    assert body["provider"] == "openrouter"
    assert provider_entry(body, "openrouter")["key_source"] == "none"


def test_removing_a_key_is_idempotent(auth_client: TestClient) -> None:
    save(auth_client, api_key=OPENROUTER_KEY)

    first = auth_client.delete(f"{SETTINGS_URL}/keys/openrouter")
    second = auth_client.delete(f"{SETTINGS_URL}/keys/openrouter")

    assert first.status_code == second.status_code == 200
    entry = provider_entry(second.json(), "openrouter")
    assert (entry["key_source"], entry["key_hint"]) == ("none", "")
    assert entry["default_model"] == CHOSEN_MODEL


@pytest.mark.parametrize(
    "body",
    [
        {"provider": "nonexistent", "providers": []},
        {"provider": "openrouter", "providers": [openrouter(default_model=TOGETHER_MODEL)]},
        {"provider": "openrouter", "providers": [openrouter(api_key="has spaces")]},
        {"provider": "openrouter", "providers": [openrouter(api_key="   ")]},
        {"provider": "openrouter", "providers": [openrouter(), openrouter()]},
    ],
)
def test_invalid_settings_are_rejected(auth_client: TestClient, body: dict[str, Any]) -> None:
    response = auth_client.put(SETTINGS_URL, json=body)
    assert response.status_code == 400
    assert response.json()["error"] == "validation_error"


def test_removing_a_key_for_an_unknown_provider_is_rejected(auth_client: TestClient) -> None:
    response = auth_client.delete(f"{SETTINGS_URL}/keys/nonexistent")
    assert response.status_code == 400
    assert response.json()["error"] == "validation_error"


def test_a_key_saved_under_another_secret_key_asks_to_be_entered_again(
    app: FastAPI, auth_client: TestClient
) -> None:
    save(auth_client, api_key=OPENROUTER_KEY)
    app.dependency_overrides[secret_box] = lambda: SecretBox("rotated-secret-key")

    response = auth_client.get("/api/models")

    assert response.status_code == 503
    assert response.json()["error"] == "provider_not_configured"
    assert "Settings page" in response.json()["detail"]
    # The Settings page itself still loads, so the key can be replaced.
    assert auth_client.get(SETTINGS_URL).status_code == 200


def test_without_any_key_the_error_points_to_the_settings_page(
    auth_client: TestClient,
) -> None:
    response = auth_client.post("/api/pipelines/generate", json={"description": "a thing"})
    assert response.status_code == 503
    assert response.json()["error"] == "provider_not_configured"
    assert "Settings page" in response.json()["detail"]


@pytest.mark.usefixtures("environment_key")
def test_a_key_in_the_environment_is_not_offered_to_accounts_by_default(
    auth_client: TestClient,
) -> None:
    entry = provider_entry(auth_client.get(SETTINGS_URL).json(), "openrouter")
    assert entry["key_source"] == "none"

    response = auth_client.post("/api/pipelines/generate", json={"description": "a thing"})

    assert response.status_code == 503
    assert response.json()["error"] == "provider_not_configured"
    assert "Settings page" in response.json()["detail"]


@pytest.mark.usefixtures("shared_environment_key")
def test_the_environment_key_serves_accounts_only_when_the_operator_allows_it(
    auth_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    built: list[ProviderConfig] = []
    plan = json.dumps({"name": "P", "steps": [{"order": 1, "prompt": "p", "model": "m"}]})

    def capture(name: str, config: ProviderConfig) -> FakeProvider:
        built.append(config)
        return FakeProvider(reply=plan)

    monkeypatch.setattr(llm_service, "create_provider", capture)

    response = auth_client.post("/api/pipelines/generate", json={"description": "a thing"})

    assert response.status_code == 200
    assert [config.api_key for config in built] == ["env-key"]


@pytest.mark.usefixtures("shared_environment_key")
def test_a_saved_key_still_wins_over_the_shared_one(
    auth_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    built: list[ProviderConfig] = []

    def capture(name: str, config: ProviderConfig) -> FakeProvider:
        built.append(config)
        return FakeProvider(reply=json.dumps({"name": "P", "steps": []}))

    monkeypatch.setattr(llm_service, "create_provider", capture)
    save(auth_client, api_key=OPENROUTER_KEY)

    auth_client.post("/api/pipelines/generate", json={"description": "a thing"})

    assert [config.api_key for config in built] == [OPENROUTER_KEY]


@pytest.mark.usefixtures("environment_key")
def test_the_cli_probe_uses_the_environment_key_whatever_accounts_may_do() -> None:
    assert llm_settings.environment_profile().api_key == "env-key"
