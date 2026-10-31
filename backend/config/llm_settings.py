"""Settings of the LLM provider layer, handed to llm/ by api.services.llm (§5 D)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from config.fields import Secret, env_aliases
from config.run_settings import TokenLimit


class LlmSettings(BaseModel):
    llm_provider: str = Field("openrouter", validation_alias="LLM_PROVIDER")
    llm_timeout_seconds: float = Field(3600.0, gt=0, validation_alias="LLM_TIMEOUT_SECONDS")
    # The planner (POST /pipelines/generate and /revise) answers inside the request,
    # so it gets a shorter timeout and a bound on what it writes.
    llm_planner_timeout_seconds: float = Field(
        300.0, gt=0, validation_alias="LLM_PLANNER_TIMEOUT_SECONDS"
    )
    llm_planner_max_output_tokens: int = Field(
        32_000, ge=1, validation_alias="LLM_PLANNER_MAX_OUTPUT_TOKENS"
    )
    # Tokens (in and out) the model calls behind one chat message may use; empty is no limit.
    chat_max_tokens: TokenLimit = Field(None, validation_alias="CHAT_MAX_TOKENS")
    # Retries of a transient provider failure (llm/retry.py); 0 turns them off.
    llm_max_retries: int = Field(2, ge=0, le=10, validation_alias="LLM_MAX_RETRIES")
    llm_retry_base_delay_seconds: float = Field(
        1.0, ge=0, validation_alias="LLM_RETRY_BASE_DELAY_SECONDS"
    )
    llm_retry_max_delay_seconds: float = Field(
        20.0, ge=0, validation_alias="LLM_RETRY_MAX_DELAY_SECONDS"
    )
    # Off: a request needs its user's own key (Settings page). On: an account with
    # no saved key spends the keys below, so only for an instance you trust everyone on.
    allow_server_llm_key: bool = Field(False, validation_alias="ALLOW_SERVER_LLM_KEY")
    openrouter_api_key: Secret = Field(
        "", validation_alias=env_aliases("OPEN_ROUTER_KEY", "OPENROUTER_API_KEY")
    )
    togetherai_api_key: Secret = Field("", validation_alias="TOGAI_API_KEY")
    meta_api_key: Secret = Field("", validation_alias="META_API_KEY")
    openrouter_base_url: str = Field("", validation_alias="OPENROUTER_BASE_URL")
    togetherai_base_url: str = Field("", validation_alias="TOGETHERAI_BASE_URL")
    meta_base_url: str = Field("", validation_alias="META_BASE_URL")
    openrouter_default_model: str = Field(
        "deepseek/deepseek-v4-flash", validation_alias="OPENROUTER_DEFAULT_MODEL"
    )
    togetherai_default_model: str = Field(
        "meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8",
        validation_alias="TOGETHERAI_DEFAULT_MODEL",
    )
    meta_default_model: str = Field("muse-spark-1.3", validation_alias="META_DEFAULT_MODEL")
    # Speech to text (the Missions microphone): Muse Voice Transcribe, on the Meta key.
    voice_model: str = Field("muse-voice-transcribe-1.0", validation_alias="VOICE_MODEL")
    voice_timeout_seconds: float = Field(60.0, gt=0, validation_alias="VOICE_TIMEOUT_SECONDS")
    # A bigger clip is refused before it is sent: 10 MB is about 5 minutes of 16 kHz WAV.
    voice_max_bytes: int = Field(10_000_000, ge=1, validation_alias="VOICE_MAX_BYTES")
    # The generate_image agent tool: Muse Image, on the Meta key ($0.01 an image).
    image_model: str = Field("muse-image-1.0", validation_alias="IMAGE_MODEL")
    image_timeout_seconds: float = Field(120.0, gt=0, validation_alias="IMAGE_TIMEOUT_SECONDS")
    # The find_objects agent tool: SAM 3.1, on the Meta key ($0.0025 a picture).
    vision_model: str = Field("sam-3.1", validation_alias="VISION_MODEL")
    vision_timeout_seconds: float = Field(60.0, gt=0, validation_alias="VISION_TIMEOUT_SECONDS")

    # Provider-keyed views, so provider lookups stay one dict access (§5 O).
    @property
    def llm_api_keys(self) -> dict[str, str]:
        return {
            "openrouter": self.openrouter_api_key,
            "togetherai": self.togetherai_api_key,
            "meta": self.meta_api_key,
        }

    @property
    def llm_base_urls(self) -> dict[str, str]:
        return {
            "openrouter": self.openrouter_base_url,
            "togetherai": self.togetherai_base_url,
            "meta": self.meta_base_url,
        }

    @property
    def llm_default_models(self) -> dict[str, str]:
        return {
            "openrouter": self.openrouter_default_model,
            "togetherai": self.togetherai_default_model,
            "meta": self.meta_default_model,
        }
