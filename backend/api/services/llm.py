"""Builds a request's LLM provider from its profile (AGENTS.md §7 Factory).

A user's saved key wins; without one, the environment's applies. This is the
only module that reads provider credentials and transport settings out of the
settings; the llm package itself receives plain values (§5 D).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from langchain_core.language_models.chat_models import BaseChatModel

from api.exceptions import ProviderNotConfigured
from api.services.catalog import available_model_ids
from config.settings import Settings, get_settings
from llm import exceptions as llm_exceptions
from llm.agent_models import create_agent_model
from llm.base import LLMProvider, ProviderConfig
from llm.catalog import CATALOGS, ModelInfo
from llm.images import ImageGenerator, MetaImageGenerator
from llm.registry import create_provider
from llm.retry import RetryPolicy
from llm.speech import MetaTranscriber, Transcriber
from llm.vision import MetaObjectFinder, ObjectFinder


@dataclass(frozen=True)
class LLMProfile:
    """Which provider, default model and key one user's requests use (§7 Value
    Object). An empty ``api_key`` means the user saved none."""

    provider: str
    default_model: str
    # Kept out of repr, so a logged or traceback-printed profile never shows it.
    api_key: str = field(default="", repr=False)

    @property
    def models(self) -> list[str]:
        """The provider's catalogue, this profile's default first."""
        return available_model_ids(self.provider, self.default_model)


def environment_key(provider: str) -> str:
    """The key in backend/.env, whatever ALLOW_SERVER_LLM_KEY says (the CLI probe's)."""
    return get_settings().llm_api_keys.get(provider, "")


def server_key(provider: str) -> str:
    """The key an account with none of its own may use: the environment's, but only
    when the operator opted in, so a key in backend/.env never opens the app to all."""
    return environment_key(provider) if get_settings().allow_server_llm_key else ""


def has_environment_key(provider: str) -> bool:
    return bool(server_key(provider))


def _retry_policy(settings: Settings) -> RetryPolicy:
    return RetryPolicy(
        max_retries=settings.llm_max_retries,
        base_delay_seconds=settings.llm_retry_base_delay_seconds,
        max_delay_seconds=settings.llm_retry_max_delay_seconds,
    )


def provider_config(profile: LLMProfile, model_id: str | None = None) -> ProviderConfig:
    settings = get_settings()
    api_key = profile.api_key or server_key(profile.provider)
    if not api_key:
        raise ProviderNotConfigured(
            f"No API key is set for {profile.provider}. Add one on the Settings page."
        )
    return ProviderConfig(
        api_key=api_key,
        default_model=model_id or profile.default_model,
        timeout_seconds=settings.llm_timeout_seconds,
        base_url=settings.llm_base_urls.get(profile.provider) or None,
        retry=_retry_policy(settings),
    )


def get_provider(profile: LLMProfile, config: ProviderConfig | None = None) -> LLMProvider:
    """Return the profile's provider (built with ``config`` when given), or raise
    a domain error the API can map."""
    try:
        return create_provider(profile.provider, config or provider_config(profile))
    except llm_exceptions.ProviderNotConfigured as cause:
        raise ProviderNotConfigured(str(cause)) from cause


def get_planner_provider(profile: LLMProfile) -> LLMProvider:
    """The provider of the pipeline planner, which answers inside the request: its
    calls time out after LLM_PLANNER_TIMEOUT_SECONDS and write at most
    LLM_PLANNER_MAX_OUTPUT_TOKENS tokens."""
    settings = get_settings()
    config = replace(
        provider_config(profile),
        timeout_seconds=settings.llm_planner_timeout_seconds,
        max_output_tokens=settings.llm_planner_max_output_tokens,
    )
    return get_provider(profile, config)


def get_agent_model(profile: LLMProfile, model_id: str | None = None) -> BaseChatModel:
    """Build a LangChain model, using a step's selected model when supplied."""
    try:
        return create_agent_model(profile.provider, provider_config(profile, model_id))
    except llm_exceptions.ProviderNotConfigured as cause:
        raise ProviderNotConfigured(str(cause)) from cause


def get_transcriber(profile: LLMProfile) -> Transcriber:
    """Speech to text on the profile's key (a Meta profile): its calls use VOICE_MODEL
    and time out after VOICE_TIMEOUT_SECONDS."""
    settings = get_settings()
    config = replace(
        provider_config(profile, settings.voice_model),
        timeout_seconds=settings.voice_timeout_seconds,
    )
    return MetaTranscriber(config)


def get_image_generator(profile: LLMProfile) -> ImageGenerator:
    """Image generation on the profile's key (a Meta profile): its calls use IMAGE_MODEL
    and time out after IMAGE_TIMEOUT_SECONDS."""
    settings = get_settings()
    config = replace(
        provider_config(profile, settings.image_model),
        timeout_seconds=settings.image_timeout_seconds,
    )
    return MetaImageGenerator(config)


def get_object_finder(profile: LLMProfile) -> ObjectFinder:
    """Object finding on the profile's key (a Meta profile): its calls use VISION_MODEL
    and time out after VISION_TIMEOUT_SECONDS."""
    settings = get_settings()
    config = replace(
        provider_config(profile, settings.vision_model),
        timeout_seconds=settings.vision_timeout_seconds,
    )
    return MetaObjectFinder(config)


def model_info(profile: LLMProfile, model_id: str) -> ModelInfo | None:
    """The catalogue entry of a model of the profile's provider (its prices)."""
    catalog = CATALOGS.get(profile.provider)
    return catalog.by_id(model_id) if catalog else None
