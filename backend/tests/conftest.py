"""Shared fixtures. Tests never reach a real provider — they inject fakes, so the
suite is deterministic and offline (AGENTS.md §6)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from concurrent.futures import Future
from pathlib import Path
from typing import Any, TypeVar

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.deps import (
    agent_factory,
    pipeline_agent_factory,
    provider_factory,
    run_executor,
    token_signer,
)
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
    allow_public_registration=True,
    # High enough that no test trips it by accident; the rate-limit tests lower it.
    user_rate_limit_requests=10_000,
    log_level="WARNING",
    llm_provider="openrouter",
    llm_timeout_seconds=1.0,
    # Retries stay on, but never wait for real.
    llm_max_retries=2,
    llm_retry_base_delay_seconds=0.0,
    llm_retry_max_delay_seconds=0.0,
    agent_timeout_seconds=1.0,
    agent_recursion_limit=9,
    mcp_timeout_seconds=1.0,
    mcp_servers={},
    # Approval gates: off for operator tools, so tools faked as MCP tools act at
    # once; the approval tests turn it on. Waits stay short and never real.
    mcp_require_approval=False,
    agent_approval_tools=[],
    approval_timeout_seconds=0.5,
    approval_poll_seconds=0.01,
    approval_arguments_max_chars=200,
    integrations_max_per_user=3,
    integrations_allow_private_network=False,
    agent_builtin_tools=["web_search", "fetch_url", "calculator", "current_datetime"],
    agent_allow_workspace_network_access=False,
    web_timeout_seconds=1.0,
    web_fetch_max_bytes=2_000,
    web_fetch_max_chars=1_000,
    web_search_max_results=3,
    # No search key: web_search stays out of the catalogue unless a test adds one.
    tavily_api_key="",
    tavily_search_url="https://search.test/search",
    # No E2B key either: run_python is never offered, so no test can reach E2B.
    e2b_api_key="",
    pipeline_max_parallel_steps=4,
    # No spending limit unless a test sets one, whatever the environment holds.
    run_default_max_cost_usd=None,
    # No scheduler thread over the shared in-memory database: test_scheduler.py
    # drives ticks itself, with its own clock.
    scheduler_enabled=False,
    schedules_max_per_user=3,
    # No free-disk reserve: a full disk on a developer's machine must not fail the
    # suite. test_file_storage.py checks the reserve with a faked disk.
    workspace_min_free_bytes=0,
    # Never the real binary: OCR tests inject a fake engine (or skip without one).
    document_ocr_enabled=False,
    openrouter_api_key="",
    togetherai_api_key="",
    meta_api_key="",
    openrouter_base_url="",
    togetherai_base_url="",
    meta_base_url="",
    openrouter_default_model="deepseek/deepseek-v4-flash",
    togetherai_default_model="meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8",
    meta_default_model="muse-spark-1.3",
)
pin_settings(TEST_SETTINGS)
#: The workspace of toolbox configs built at import time. It cannot be created,
#: so workspace tools are never offered from it: tests that need files use tmp_path.
UNUSED_WORKSPACE = Path("/nonexistent/aimix-test-workspace")


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

    async def execute(self, task: AgentTask) -> AgentOutcome:
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

    async def execute(self, task: AgentTask) -> AgentOutcome:
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


T = TypeVar("T")


class InlineRunExecutor:
    """Runs each job to its end inside ``submit``, so a test sees the finished
    run as soon as the request returns. Nothing is ever left to cancel."""

    def __init__(self) -> None:
        self.keys: list[int] = []

    def submit(self, key: int, job: Callable[[], Awaitable[T]]) -> Future[T]:
        self.keys.append(key)
        future: Future[T] = Future()

        async def main() -> T:
            return await job()

        future.set_result(asyncio.run(main()))
        return future

    def cancel(self, key: int) -> None:
        return None

    def settled(self, key: int) -> bool:
        return True

    def shutdown(self) -> None:
        return None


def use_inline_runs(app: FastAPI) -> InlineRunExecutor:
    """Execute runs inside the request, deterministically."""
    executor = InlineRunExecutor()
    app.dependency_overrides[run_executor] = lambda: executor
    return executor


def tool_call(name: str, args: dict[str, Any], call_id: str = "call-1") -> dict[str, Any]:
    """A tool invocation shaped as the agent sends it, so errors become messages."""
    return {"type": "tool_call", "id": call_id, "name": name, "args": args}


def use_agent(app: FastAPI, agent: ChatAgent) -> None:
    app.dependency_overrides[agent_factory] = lambda: lambda: agent


def use_provider(app: FastAPI, provider: LLMProvider) -> None:
    """Make every endpoint that needs a provider get this one."""
    app.dependency_overrides[provider_factory] = lambda: lambda: provider


def use_pipeline_generator(app: FastAPI, generator: StepGenerator) -> None:
    app.dependency_overrides[pipeline_agent_factory] = lambda: lambda: generator


@pytest.fixture
def app() -> Iterator[FastAPI]:
    """A fresh app over a fresh in-memory database for every test. Runs
    execute inline (see ``InlineRunExecutor``); test_runs_service.py covers
    the background executor."""
    application = create_app()
    engine = application.state.database.engine
    Base.metadata.create_all(engine)
    use_inline_runs(application)
    yield application
    application.state.run_executor.shutdown()
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
    token = token_signer(TEST_SETTINGS).issue(user.id, "access", user.token_version)
    return {"Authorization": f"Bearer {token}"}


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
