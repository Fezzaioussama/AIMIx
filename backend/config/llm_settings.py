"""Settings of the LLM provider layer, handed to llm/ by api.services.llm (§5 D)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from config.fields import Secret, env_aliases


class LlmSettings(BaseModel):
    llm_provider: str = Field("openrouter", validation_alias="LLM_PROVIDER")
    llm_timeout_seconds: float = Field(3600.0, gt=0, validation_alias="LLM_TIMEOUT_SECONDS")
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
    openrouter_base_url: str = Field("", validation_alias="OPENROUTER_BASE_URL")
    togetherai_base_url: str = Field("", validation_alias="TOGETHERAI_BASE_URL")
    openrouter_default_model: str = Field(
        "deepseek/deepseek-v4-flash", validation_alias="OPENROUTER_DEFAULT_MODEL"
    )
    togetherai_default_model: str = Field(
        "meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8",
        validation_alias="TOGETHERAI_DEFAULT_MODEL",
    )

    # Provider-keyed views, so provider lookups stay one dict access (§5 O).
    @property
    def llm_api_keys(self) -> dict[str, str]:
        return {"openrouter": self.openrouter_api_key, "togetherai": self.togetherai_api_key}

    @property
    def llm_base_urls(self) -> dict[str, str]:
        return {"openrouter": self.openrouter_base_url, "togetherai": self.togetherai_base_url}

    @property
    def llm_default_models(self) -> dict[str, str]:
        return {
            "openrouter": self.openrouter_default_model,
            "togetherai": self.togetherai_default_model,
        }
