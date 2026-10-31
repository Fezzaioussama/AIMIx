"""The LangChain models behind chat and pipeline steps retry under the
configured policy, and only it: each SDK's own retries are switched off.

Offline throughout: the real integrations over a stubbed HTTP send, or with
their own streaming method replaced by a script.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, replace
from typing import Any

import httpx
import httpx2
import openai
import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_openai import ChatOpenAI
from langchain_openrouter import ChatOpenRouter
from langchain_together import ChatTogether
from openrouter.errors import OpenRouterError

from api.exceptions import ProviderUnavailable
from api.services import agent_runtime
from api.services.agent import LangGraphChatAgent
from api.services.agent_runtime import AgentLimits, AgentToolset, as_agent_error
from llm.agent_models import create_agent_model
from llm.retry import RetryPolicy
from tests.retry_fakes import CONFIG, INSTANT, openrouter_status

BUSY = {"error": {"code": 503, "message": "busy"}}
Script = tuple[list[str], Exception | None]


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """These models hold a real-looking key: any send a test did not stub fails."""

    def refuse(self: Any, request: Any, **kwargs: Any) -> Any:
        raise AssertionError(f"unexpected network call to {request.url}")

    async def refuse_async(self: Any, request: Any, **kwargs: Any) -> Any:
        refuse(self, request)

    for library in (httpx, httpx2):
        monkeypatch.setattr(library.Client, "send", refuse)
        monkeypatch.setattr(library.AsyncClient, "send", refuse_async)


def test_agent_models_switch_their_sdk_retries_off() -> None:
    openrouter_model: Any = create_agent_model("openrouter", CONFIG)
    together_model: Any = create_agent_model("togetherai", CONFIG)
    meta_model: Any = create_agent_model("meta", CONFIG)
    # Left alone, the openrouter SDK retries 5xx and timeouts for up to an hour.
    assert openrouter_model.client.sdk_configuration.retry_config is None
    for openai_model in (together_model, meta_model):
        assert openai_model.root_client.max_retries == 0
        assert openai_model.root_async_client.max_retries == 0


@pytest.mark.parametrize("integration", [ChatOpenRouter, ChatTogether, ChatOpenAI])
def test_each_integration_implements_every_call_path(integration: type[BaseChatModel]) -> None:
    """Otherwise BaseChatModel's async fallback would run the retrying sync
    method inside the retrying async one, and the retries would multiply."""
    for method in ("_generate", "_agenerate", "_stream", "_astream"):
        assert getattr(integration, method) is not getattr(BaseChatModel, method)


async def _busy_over_httpx(self: Any, request: httpx.Request, **kw: Any) -> httpx.Response:
    return httpx.Response(503, json=BUSY, request=request)


async def _busy_over_httpx2(self: Any, request: httpx2.Request, **kw: Any) -> httpx2.Response:
    return httpx2.Response(503, json=BUSY, request=request)


@dataclass(frozen=True)
class Sdk:
    """One integration's HTTP library, a stub answering 503, and the SDK's error."""

    provider: str
    http_client: type[Any]
    busy: Callable[..., Any]
    error: type[Exception]


SDKS = [
    Sdk("openrouter", httpx.AsyncClient, _busy_over_httpx, OpenRouterError),
    Sdk("togetherai", httpx2.AsyncClient, _busy_over_httpx2, openai.InternalServerError),
    Sdk("meta", httpx2.AsyncClient, _busy_over_httpx2, openai.InternalServerError),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("sdk", SDKS, ids=lambda sdk: sdk.provider)
async def test_agent_models_make_exactly_the_configured_attempts(
    monkeypatch: pytest.MonkeyPatch, sdk: Sdk
) -> None:
    attempts: list[str] = []

    async def counted(self: Any, request: Any, **kw: Any) -> Any:
        attempts.append(str(request.url))
        # A third attempt is a hidden SDK retry: fail now rather than sit out its backoff.
        assert len(attempts) <= 2, "the SDK retried on its own"
        return await sdk.busy(self, request, **kw)

    monkeypatch.setattr(sdk.http_client, "send", counted)
    model = create_agent_model(sdk.provider, replace(INSTANT, retry=RetryPolicy(1, 0.0, 0.0)))

    with pytest.raises(sdk.error) as raised:
        await model.ainvoke("hello")

    assert len(attempts) == 2  # one retry, and no hidden SDK retries
    # The agents' error mapping is unchanged: the SDK's own error still surfaces.
    assert isinstance(as_agent_error(raised.value), ProviderUnavailable)


def script_openrouter(monkeypatch: pytest.MonkeyPatch, *scripts: Script) -> list[str]:
    """Replace ChatOpenRouter's own provider calls: each call, streamed or not,
    plays the next script (pieces, then an optional error). Returns the calls."""
    calls: list[str] = []

    def play(kind: str) -> Script:
        calls.append(kind)
        return scripts[len(calls) - 1]

    async def agenerate(self: Any, *args: Any, **kwargs: Any) -> ChatResult:
        pieces, error = play("agenerate")
        if error is not None:
            raise error
        return ChatResult(generations=[ChatGeneration(message=AIMessage("".join(pieces)))])

    async def astream(self: Any, *args: Any, **kwargs: Any) -> AsyncIterator[ChatGenerationChunk]:
        pieces, error = play("astream")
        for piece in pieces:
            yield ChatGenerationChunk(message=AIMessageChunk(content=piece))
        if error is not None:
            raise error

    monkeypatch.setattr(ChatOpenRouter, "_agenerate", agenerate)
    monkeypatch.setattr(ChatOpenRouter, "_astream", astream)
    return calls


@pytest.mark.asyncio
async def test_an_agent_model_stream_is_retried_before_its_first_chunk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = script_openrouter(monkeypatch, ([], openrouter_status(502)), (["Hel", "lo"], None))
    model = create_agent_model("openrouter", INSTANT)
    assert "".join([str(chunk.content) async for chunk in model.astream("hi")]) == "Hello"
    assert calls == ["astream", "astream"]


@pytest.mark.asyncio
async def test_an_agent_model_stream_is_not_replayed_after_its_first_chunk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = script_openrouter(monkeypatch, (["Hel"], openrouter_status(502)), (["Hello"], None))
    model = create_agent_model("openrouter", INSTANT)
    received: list[str] = []
    with pytest.raises(OpenRouterError):
        async for chunk in model.astream("hi"):
            received.append(str(chunk.content))
    assert ("".join(received), calls) == ("Hel", ["astream"])


@pytest.mark.asyncio
async def test_the_chat_agent_delivers_a_retried_reply_exactly_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def no_tools(configured: object, native: list[Any], timeout: float) -> list[Any]:
        return []

    calls = script_openrouter(monkeypatch, ([], openrouter_status(503)), (["Hel", "lo"], None))
    monkeypatch.setattr(agent_runtime, "discover_tools", no_tools)
    model = create_agent_model("openrouter", INSTANT)
    agent = LangGraphChatAgent(model, AgentToolset({}, []), AgentLimits(10, 9, 1))

    assert "".join([part async for part in agent.stream("hi")]) == "Hello"
    assert len(calls) == 2
