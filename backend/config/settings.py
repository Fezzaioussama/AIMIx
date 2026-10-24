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

#: Headroom over a document's size for the multipart framing around it.
MULTIPART_OVERHEAD_BYTES = 1_048_576

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
    # Built React app (frontend/dist) to serve next to /api; empty serves none.
    frontend_dist_dir: str = Field("", validation_alias="FRONTEND_DIST_DIR")

    jwt_access_minutes: float = Field(60, gt=0, validation_alias="JWT_ACCESS_MINUTES")
    jwt_refresh_days: float = Field(1, gt=0, validation_alias="JWT_REFRESH_DAYS")
    refresh_cookie_name: str = Field(
        "aimix_refresh", min_length=1, validation_alias="REFRESH_COOKIE_NAME"
    )
    # Django 5.2's PBKDF2 work factor, so imported and new hashes match.
    password_hash_iterations: int = Field(
        1_000_000, ge=1, validation_alias="PASSWORD_HASH_ITERATIONS"
    )
    allow_public_registration: bool = Field(False, validation_alias="ALLOW_PUBLIC_REGISTRATION")
    auth_rate_limit_requests: int = Field(20, ge=1, validation_alias="AUTH_RATE_LIMIT_REQUESTS")
    auth_rate_limit_window_seconds: int = Field(
        60, ge=1, validation_alias="AUTH_RATE_LIMIT_WINDOW_SECONDS"
    )

    # --- LLM provider layer: handed to llm/ by api.services.llm (§5 D) -------
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
    agent_timeout_seconds: float = Field(3600.0, gt=0, validation_alias="AGENT_TIMEOUT_SECONDS")
    agent_recursion_limit: int = Field(25, ge=2, validation_alias="AGENT_RECURSION_LIMIT")
    agent_tool_description_max_chars: int = Field(
        300, ge=1, validation_alias="AGENT_TOOL_DESCRIPTION_MAX_CHARS"
    )
    mcp_timeout_seconds: float = Field(30.0, gt=0, validation_alias="MCP_TIMEOUT_SECONDS")
    mcp_servers: dict[str, MCPServer] = Field(default_factory=dict, validation_alias="MCP_SERVERS")
    # --- Built-in agent tools (api/services/toolbox) --------------------------
    agent_builtin_tools: CommaList = Field(
        [
            "web_search",
            "fetch_url",
            "calculator",
            "current_datetime",
            "list_workspace_files",
            "read_workspace_file",
            "search_workspace_files",
            "read_csv",
            "save_artifact",
        ],
        validation_alias="AGENT_BUILTIN_TOOLS",
    )
    # Explicit opt-in: otherwise file-reading tools suppress outbound web tools,
    # preventing model-driven disclosure of workspace data.
    agent_allow_workspace_network_access: bool = Field(
        False, validation_alias="AGENT_ALLOW_WORKSPACE_NETWORK_ACCESS"
    )
    web_timeout_seconds: float = Field(15.0, gt=0, validation_alias="WEB_TIMEOUT_SECONDS")
    web_fetch_max_bytes: int = Field(2_000_000, ge=1, validation_alias="WEB_FETCH_MAX_BYTES")
    web_fetch_max_chars: int = Field(20_000, ge=1, validation_alias="WEB_FETCH_MAX_CHARS")
    web_search_max_results: int = Field(5, ge=1, le=20, validation_alias="WEB_SEARCH_MAX_RESULTS")
    tavily_api_key: str = Field("", validation_alias="TAVILY_API_KEY")
    tavily_search_url: str = Field(
        "https://api.tavily.com/search", validation_alias="TAVILY_SEARCH_URL"
    )
    workspace_dir: Path = Field(BASE_DIR / "workspace", validation_alias="AGENT_WORKSPACE_DIR")
    workspace_max_file_bytes: int = Field(
        2_000_000, ge=1, validation_alias="WORKSPACE_MAX_FILE_BYTES"
    )
    workspace_max_output_chars: int = Field(
        20_000, ge=1, validation_alias="WORKSPACE_MAX_OUTPUT_CHARS"
    )
    workspace_search_max_files: int = Field(
        200, ge=1, validation_alias="WORKSPACE_SEARCH_MAX_FILES"
    )
    workspace_search_max_results: int = Field(
        50, ge=1, validation_alias="WORKSPACE_SEARCH_MAX_RESULTS"
    )
    workspace_csv_max_rows: int = Field(200, ge=1, validation_alias="WORKSPACE_CSV_MAX_ROWS")
    # --- Documents attached to a pipeline run (api/services/documents) --------
    # An upload is read into memory, so each of these bounds a different cost.
    document_max_bytes: int = Field(10_000_000, ge=1, validation_alias="DOCUMENT_MAX_BYTES")
    # Text kept from one document; the rest is dropped and the run is told so.
    document_max_chars: int = Field(120_000, ge=1, validation_alias="DOCUMENT_MAX_CHARS")
    document_max_pages: int = Field(300, ge=1, validation_alias="DOCUMENT_MAX_PAGES")
    # A .docx is a zip: refuse one that would unpack to more than this.
    document_max_unpacked_bytes: int = Field(
        50_000_000, ge=1, validation_alias="DOCUMENT_MAX_UNPACKED_BYTES"
    )
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

    @field_validator("allowed_hosts", "cors_allowed_origins", "agent_builtin_tools", mode="before")
    @classmethod
    def _split_commas(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator(
        "openrouter_api_key", "togetherai_api_key", "tavily_api_key", "secret_key", mode="after"
    )
    @classmethod
    def _drop_placeholders(cls, value: str) -> str:
        value = value.strip()
        return "" if value.lower() in SECRET_PLACEHOLDERS else value

    @field_validator("log_level", mode="after")
    @classmethod
    def _upper(cls, value: str) -> str:
        return value.upper()

    @field_validator("workspace_dir", mode="after")
    @classmethod
    def _workspace_path(cls, value: Path) -> Path:
        return value if value.is_absolute() else BASE_DIR / value

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

    @property
    def max_request_bytes(self) -> int:
        """Largest request body accepted: one document plus multipart overhead."""
        return self.document_max_bytes + MULTIPART_OVERHEAD_BYTES

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
