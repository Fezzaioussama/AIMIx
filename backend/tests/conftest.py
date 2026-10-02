"""Shared fixtures. Tests never reach a real provider — they inject fakes, so the
suite is deterministic and offline (AGENTS.md §6)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.deps import agent_factory, pipeline_agent_factory, provider_factory, token_signer
from api.main import create_app
from api.models import Base, User
from api.repositories import users
from api.security import hash_password
from api.services.agent_types import AgentOutcome, AgentTask
from api.services.chat import ChatAgent
from api.services.pipelines import StepGenerator
from config.settings import Settings, pin_settings
from llm import exceptions as llm_exceptions
from llm.base import LLMProvider

#: Pinned before any app is built, so no .env value can change a test's outcome.
TEST_SETTINGS = Settings(
    _env_file=None,
    app_env="test",
    debug=False,
    secret_key="testing-key-not-used-outside-tests",
    allowed_hosts=["testserver"],
    database_url="sqlite://",
    # Hashing is the slowest part of auth-heavy tests.
    password_hash_iterations=1,
    log_level="WARNING",
    llm_provider="openrouter",
    llm_timeout_seconds=1.0,
    agent_timeout_seconds=1.0,
    agent_recursion_limit=9,
    mcp_timeout_seconds=1.0,
    mcp_servers={},
    pipeline_max_parallel_steps=4,
    openrouter_api_key="",
    togetherai_api_key="",
    openrouter_base_url="",
    togetherai_base_url="",
    openrouter_default_model="deepseek/deepseek-v4-flash",
    togetherai_default_model="meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8",
)
pin_settings(TEST_SETTINGS)


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

    def execute(self, task: AgentTask) -> AgentOutcome:
        return AgentOutcome(self.generate(task.prompt, task.model), [])

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

    def execute(self, task: AgentTask) -> AgentOutcome:
        return AgentOutcome(self.generate(task.prompt, task.model), [])

    def stream(self, prompt: str, model: str | None = None) -> Iterator[str]:
        raise self.error
        yield ""  # pragma: no cover - unreachable, keeps this a generator


class FakeAgent:
    def __init__(self, chunks: list[str] | None = None) -> None:
        self.chunks = chunks if chunks is not None else ["fake ", "reply"]
        self.prompts: list[str] = []

    async def stream(self, prompt: str) -> AsyncIterator[str]:
        self.prompts.append(prompt)
        for chunk in self.chunks:
            yield chunk


def use_agent(app: FastAPI, agent: ChatAgent) -> None:
    app.dependency_overrides[agent_factory] = lambda: lambda: agent


def use_provider(app: FastAPI, provider: LLMProvider) -> None:
    """Make every endpoint that needs a provider get this one."""
    app.dependency_overrides[provider_factory] = lambda: lambda: provider


def use_pipeline_generator(app: FastAPI, generator: StepGenerator) -> None:
    app.dependency_overrides[pipeline_agent_factory] = lambda: lambda: generator


@pytest.fixture
def app() -> Iterator[FastAPI]:
    """A fresh app over a fresh in-memory database for every test."""
    application = create_app()
    engine = application.state.database.engine
    Base.metadata.create_all(engine)
    yield application
    engine.dispose()


@pytest.fixture
def session(app: FastAPI) -> Iterator[Session]:
    with app.state.database.session() as db:
        yield db


@pytest.fixture
def password() -> str:
    return "pipeline-test-pass-123"


@pytest.fixture
def user(session: Session, password: str) -> User:
    return users.create(session, "tester", hash_password(password, 1))


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def bearer(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {token_signer(TEST_SETTINGS).issue(user.id, 'access')}"}


@pytest.fixture
def auth_client(client: TestClient, user: User) -> TestClient:
    client.headers.update(bearer(user))
    return client


@pytest.fixture
def fake_provider(app: FastAPI) -> FakeProvider:
    provider = FakeProvider()
    use_provider(app, provider)
    use_pipeline_generator(app, provider)
    return provider


@pytest.fixture
def default_model() -> str:
    from api.services.catalog import default_model_id

    return default_model_id()
