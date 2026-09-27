"""Shared fixtures. Tests never reach a real provider — they inject fakes, so the
suite is deterministic and offline (AGENTS.md §6)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from llm import exceptions as llm_exceptions


class FakeProvider:
    """Implements the LLMProvider protocol with canned output."""

    name = "fake"

    def __init__(self, reply: str = "fake reply", chunks: list[str] | None = None) -> None:
        self.reply = reply
        self.chunks = chunks if chunks is not None else ["fake ", "reply"]
        self.calls: list[tuple[str, str | None]] = []

    def generate(self, prompt: str, model: str | None = None) -> str:
        self.calls.append((prompt, model))
        return self.reply

    def stream(self, prompt: str, model: str | None = None) -> Iterator[str]:
        self.calls.append((prompt, model))
        yield from self.chunks


class FailingProvider:
    """Raises a chosen provider error on every call."""

    name = "failing"

    def __init__(self, error: llm_exceptions.LLMError) -> None:
        self.error = error

    def generate(self, prompt: str, model: str | None = None) -> str:
        raise self.error

    def stream(self, prompt: str, model: str | None = None) -> Iterator[str]:
        raise self.error
        yield ""  # pragma: no cover - unreachable, keeps this a generator


@pytest.fixture
def password() -> str:
    return "pipeline-test-pass-123"


@pytest.fixture
def user(db, password: str) -> User:
    return User.objects.create_user(username="tester", password=password)


@pytest.fixture
def client() -> APIClient:
    return APIClient()


@pytest.fixture
def auth_client(client: APIClient, user: User) -> APIClient:
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def fake_provider(monkeypatch: pytest.MonkeyPatch) -> FakeProvider:
    """Replace the provider factory everywhere the endpoints look it up."""
    provider = FakeProvider()
    monkeypatch.setattr("api.endpoints.pipelines.get_provider", lambda: provider)
    monkeypatch.setattr("api.endpoints.chat.get_provider", lambda: provider)
    return provider


@pytest.fixture
def default_model() -> str:
    from api.services.catalog import default_model_id

    return default_model_id()
