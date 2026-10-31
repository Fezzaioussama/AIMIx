"""LangChain chat models for the LangGraph agent (Registry strategy).

Each model is the provider's LangChain integration with the retry policy of
``llm/retry.py`` mixed in and its SDK's own retries switched off.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Iterator
from math import ceil
from typing import Any

from langchain_core.callbacks import AsyncCallbackManagerForLLMRun, CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatGenerationChunk, ChatResult
from langchain_openai import ChatOpenAI
from langchain_openrouter import ChatOpenRouter
from langchain_together import ChatTogether
from pydantic import Field

from llm.base import ProviderConfig
from llm.exceptions import ProviderNotConfigured
from llm.providers import meta, openrouter, together
from llm.registry import canonical_name
from llm.retry import Retrier


class RetryingChatModel(BaseChatModel):
    """Runs a LangChain chat model's provider calls under the retry policy (§6).

    Mixed in ahead of a concrete model (a Decorator, by inheritance), it wraps
    the four methods every LangChain call ends in. A stream is retried only
    until its first chunk, because each chunk goes to the callbacks, and on to
    whoever streams the reply, as soon as it arrives. ``streaming`` stays False
    (the default): otherwise ``_generate`` would stream inside a retry that
    could replay chunks.
    """

    retrier: Retrier = Field(exclude=True)

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        # Abstract on BaseChatModel, but always mixed in ahead of a concrete model.
        generate = super()._generate  # type: ignore[safe-super]
        return self.retrier.call(lambda: generate(messages, stop, run_manager, **kwargs))

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        agenerate = super()._agenerate
        return await self.retrier.acall(lambda: agenerate(messages, stop, run_manager, **kwargs))

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        stream = super()._stream
        return self.retrier.stream(lambda: stream(messages, stop, run_manager, **kwargs))

    def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        astream = super()._astream
        return self.retrier.astream(lambda: astream(messages, stop, run_manager, **kwargs))


class RetryingChatOpenRouter(RetryingChatModel, ChatOpenRouter):
    """ChatOpenRouter under the retry policy."""

    def _build_client(self) -> Any:
        # With max_retries=0 ChatOpenRouter passes no retry config, and the
        # openrouter SDK then applies its own: 5xx, dropped connections and
        # timeouts retried for up to an hour. None switches that off.
        client = super()._build_client()
        client.sdk_configuration.retry_config = None
        return client


class RetryingChatTogether(RetryingChatModel, ChatTogether):
    """ChatTogether under the retry policy; ``max_retries=0`` is the openai SDK's off switch."""


class RetryingChatMeta(RetryingChatModel, ChatOpenAI):
    """ChatOpenAI pointed at the Meta Model API (it has no LangChain integration of
    its own) under the retry policy; ``max_retries=0`` is the openai SDK's off switch."""


def _retrier(provider: str, config: ProviderConfig) -> Retrier:
    return Retrier(config.retry, provider, config.default_model)


def _openrouter(config: ProviderConfig) -> BaseChatModel:
    if not config.api_key:
        raise ProviderNotConfigured("OPEN_ROUTER_KEY is not set.")
    return RetryingChatOpenRouter(
        model_name=config.default_model,
        api_key=config.api_key,
        base_url=config.base_url or openrouter.DEFAULT_BASE_URL,
        request_timeout=ceil(config.timeout_seconds * 1000),
        max_retries=0,
        retrier=_retrier(openrouter.NAME, config),
    )


def _together(config: ProviderConfig) -> BaseChatModel:
    if not config.api_key:
        raise ProviderNotConfigured("TOGAI_API_KEY is not set.")
    base_url = {"base_url": config.base_url} if config.base_url else {}
    return RetryingChatTogether(
        model=config.default_model,
        api_key=config.api_key,
        **base_url,
        timeout=config.timeout_seconds,
        max_retries=0,
        retrier=_retrier(together.NAME, config),
    )


def _meta(config: ProviderConfig) -> BaseChatModel:
    if not config.api_key:
        raise ProviderNotConfigured("META_API_KEY is not set.")
    return RetryingChatMeta(
        model=config.default_model,
        api_key=config.api_key,
        base_url=config.base_url or meta.DEFAULT_BASE_URL,
        timeout=config.timeout_seconds,
        max_retries=0,
        # The API sends a stream's usage only when asked, and ChatOpenAI asks only
        # OpenAI itself: without this a chat message's calls would go uncounted.
        stream_usage=True,
        retrier=_retrier(meta.NAME, config),
    )


AGENT_MODELS: dict[str, Callable[[ProviderConfig], BaseChatModel]] = {
    openrouter.NAME: _openrouter,
    together.NAME: _together,
    meta.NAME: _meta,
}


def create_agent_model(provider: str, config: ProviderConfig) -> BaseChatModel:
    return AGENT_MODELS[canonical_name(provider)](config)
