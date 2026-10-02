"""Typed application settings, read from the environment and ``backend/.env``.

The single source of every tuning value, URL and credential (AGENTS.md §6).
Variables formerly prefixed ``DJANGO_`` are still accepted under that name, so
an existing ``.env`` keeps working.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import AliasChoices, BaseModel, Field, HttpUrl, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[1]

#: Values that look like a filled-in credential but are not one. Treating these
#: as unset means a half-configured .env fails fast with "not configured"
#: instead of sending a doomed request and reporting an upstream 401.
SECRET_PLACEHOLDERS = frozenset(
    {
        "change-me",
        "changeme",
        "your-api-key",
        "your-api-key-here",
        "your_api_key",
        "your_api_key_here",
    }
)

#: Only acceptable when APP_ENV=local; production refuses to start without a key.
LOCAL_SECRET_KEY = "insecure-local-development-key-change-me"

CommaList = Annotated[list[str], NoDecode]


class HttpMCPServer(BaseModel):
    transport: Literal["streamable_http"]
    url: HttpUrl
    headers: dict[str, str] = Field(default_factory=dict)


class StdioMCPServer(BaseModel):
    transport: Literal["stdio"]
    command: str = Field(min_length=1)
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)


MCPServer = Annotated[HttpMCPServer | StdioMCPServer, Field(discriminator="transport")]


def _env(*names: str) -> AliasChoices:
    """Accept a variable under its current name and any legacy spelling."""
    return AliasChoices(*names)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        extra="ignore",
        populate_by_name=True,
    )

    app_env: Literal["local", "production", "test"] = Field("local", validation_alias="APP_ENV")
    debug: bool = Field(False, validation_alias=_env("DEBUG", "DJANGO_DEBUG"))
    secret_key: str = Field("", validation_alias=_env("SECRET_KEY", "DJANGO_SECRET_KEY"))
    allowed_hosts: CommaList = Field(
        ["localhost", "127.0.0.1"],
        validation_alias=_env("ALLOWED_HOSTS", "DJANGO_ALLOWED_HOSTS"),
    )
    cors_allowed_origins: CommaList = Field(
        ["http://localhost:4200", "http://127.0.0.1:4200"],
        validation_alias=_env("CORS_ALLOWED_ORIGINS", "DJANGO_CORS_ALLOWED_ORIGINS"),
    )
    database_url: str = Field(
        f"sqlite:///{BASE_DIR / 'aimix.sqlite3'}", validation_alias="DATABASE_URL"
    )
    log_level: str = Field("INFO", validation_alias=_env("LOG_LEVEL", "DJANGO_LOG_LEVEL"))

    jwt_access_minutes: float = Field(60, gt=0, validation_alias="JWT_ACCESS_MINUTES")
    jwt_refresh_days: float = Field(1, gt=0, validation_alias="JWT_REFRESH_DAYS")
    # Django 5.2's PBKDF2 work factor, so imported and new hashes match.
    password_hash_iterations: int = Field(
        1_000_000, ge=1, validation_alias="PASSWORD_HASH_ITERATIONS"
    )

    # --- LLM provider layer: handed to llm/ by api.services.llm (§5 D) -------
    llm_provider: str = Field("openrouter", validation_alias="LLM_PROVIDER")
    llm_timeout_seconds: float = Field(3600.0, gt=0, validation_alias="LLM_TIMEOUT_SECONDS")
    agent_timeout_seconds: float = Field(3600.0, gt=0, validation_alias="AGENT_TIMEOUT_SECONDS")
    agent_recursion_limit: int = Field(25, ge=2, validation_alias="AGENT_RECURSION_LIMIT")
    agent_tool_description_max_chars: int = Field(
        300, ge=1, validation_alias="AGENT_TOOL_DESCRIPTION_MAX_CHARS"
    )
    mcp_timeout_seconds: float = Field(30.0, gt=0, validation_alias="MCP_TIMEOUT_SECONDS")
    mcp_servers: dict[str, MCPServer] = Field(default_factory=dict, validation_alias="MCP_SERVERS")
    # Upper bound on provider calls one pipeline run makes at once for a stage
    # whose steps run in parallel.
    pipeline_max_parallel_steps: int = Field(
        4, ge=1, validation_alias="PIPELINE_MAX_PARALLEL_STEPS"
    )
    openrouter_api_key: str = Field(
        "", validation_alias=_env("OPEN_ROUTER_KEY", "OPENROUTER_API_KEY")
    )
    togetherai_api_key: str = Field("", validation_alias="TOGAI_API_KEY")
    openrouter_base_url: str = Field("", validation_alias="OPENROUTER_BASE_URL")
    togetherai_base_url: str = Field("", validation_alias="TOGETHERAI_BASE_URL")
    openrouter_default_model: str = Field(
        "deepseek/deepseek-v4-flash", validation_alias="OPENROUTER_DEFAULT_MODEL"
    )
    togetherai_default_model: str = Field(
        "meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8",
        validation_alias="TOGETHERAI_DEFAULT_MODEL",
    )

    @field_validator("allowed_hosts", "cors_allowed_origins", mode="before")
    @classmethod
    def _split_commas(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("openrouter_api_key", "togetherai_api_key", "secret_key", mode="after")
    @classmethod
    def _drop_placeholders(cls, value: str) -> str:
        value = value.strip()
        return "" if value.lower() in SECRET_PLACEHOLDERS else value

    @field_validator("log_level", mode="after")
    @classmethod
    def _upper(cls, value: str) -> str:
        return value.upper()

    @model_validator(mode="after")
    def _check_environment(self) -> Settings:
        """Fail fast on unsafe production configuration (§6)."""
        if self.app_env == "production":
            if self.debug:
                raise ValueError("DEBUG must be false in production.")
            if not self.secret_key:
                raise ValueError("SECRET_KEY must be set in production.")
            if not self.allowed_hosts:
                raise ValueError("ALLOWED_HOSTS must list at least one host.")
        elif not self.secret_key:
            self.secret_key = LOCAL_SECRET_KEY
        return self

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


_pinned: Settings | None = None


def get_settings() -> Settings:
    """The process-wide settings: pinned ones if set, else the environment's."""
    return _pinned or _from_environment()


def pin_settings(settings: Settings | None) -> None:
    """Fix the settings for this process (tests, one-off tools); None unpins."""
    global _pinned
    _pinned = settings


@lru_cache(maxsize=1)
def _from_environment() -> Settings:
    return Settings()
