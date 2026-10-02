"""LangChain chat models for the LangGraph agent (Registry strategy)."""

from __future__ import annotations

from collections.abc import Callable
from math import ceil

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openrouter import ChatOpenRouter
from langchain_together import ChatTogether

from llm.base import ProviderConfig
from llm.exceptions import ProviderNotConfigured
from llm.providers import openrouter, together
from llm.registry import canonical_name


def _openrouter(config: ProviderConfig) -> BaseChatModel:
    if not config.api_key:
        raise ProviderNotConfigured("OPEN_ROUTER_KEY is not set.")
    return ChatOpenRouter(
        model_name=config.default_model,
        api_key=config.api_key,
        base_url=config.base_url or openrouter.DEFAULT_BASE_URL,
        request_timeout=ceil(config.timeout_seconds * 1000),
        max_retries=0,
    )


def _together(config: ProviderConfig) -> BaseChatModel:
    if not config.api_key:
        raise ProviderNotConfigured("TOGAI_API_KEY is not set.")
    base_url = {"base_url": config.base_url} if config.base_url else {}
    return ChatTogether(
        model=config.default_model,
        api_key=config.api_key,
        **base_url,
        timeout=config.timeout_seconds,
        max_retries=0,
    )


AGENT_MODELS: dict[str, Callable[[ProviderConfig], BaseChatModel]] = {
    openrouter.NAME: _openrouter,
    together.NAME: _together,
}


def create_agent_model(provider: str, config: ProviderConfig) -> BaseChatModel:
    return AGENT_MODELS[canonical_name(provider)](config)
