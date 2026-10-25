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
    # --- Approval gates (api/services/approvals) ------------------------------
    # Tools of MCP_SERVERS wait for the run owner's OK before they act.
    mcp_require_approval: bool = Field(True, validation_alias="MCP_REQUIRE_APPROVAL")
    # Built-in tools (AGENT_BUILTIN_TOOLS names) that wait for the owner's OK too.
    agent_approval_tools: CommaList = Field([], validation_alias="AGENT_APPROVAL_TOOLS")
    # An unanswered request expires (counts as declined) after this long; the
    # step's AGENT_TIMEOUT_SECONDS still bounds the wait.
    approval_timeout_seconds: float = Field(
        1800.0, gt=0, validation_alias="APPROVAL_TIMEOUT_SECONDS"
    )
    # How often a waiting run checks the database for the owner's decision.
    approval_poll_seconds: float = Field(1.0, gt=0, validation_alias="APPROVAL_POLL_SECONDS")
    # A tool call's arguments are kept for the owner to read, cut at this length.
    approval_arguments_max_chars: int = Field(
        4000, ge=1, validation_alias="APPROVAL_ARGUMENTS_MAX_CHARS"
    )
    # --- Users' own MCP servers (Settings page → Integrations) ---------------
    integrations_max_per_user: int = Field(10, ge=0, validation_alias="INTEGRATIONS_MAX_PER_USER")
    # Local development only: let integrations reach loopback and private
    # addresses (e.g. a server on 127.0.0.1). Production refuses to start with it.
    integrations_allow_private_network: bool = Field(
        False, validation_alias="INTEGRATIONS_ALLOW_PRIVATE_NETWORK"
    )
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
            "run_python",
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
    # --- Code sandbox behind run_python (api/services/toolbox/sandbox.py) -----
    # Empty: run_python is not offered. Each call sends its code and input files to E2B.
    e2b_api_key: str = Field("", validation_alias="E2B_API_KEY")
    # Bounds one call (creating its sandbox, moving files, running the code) and
    # the sandbox's lifetime.
    sandbox_timeout_seconds: float = Field(60.0, gt=0, validation_alias="SANDBOX_TIMEOUT_SECONDS")
    sandbox_max_output_chars: int = Field(10_000, ge=1, validation_alias="SANDBOX_MAX_OUTPUT_CHARS")
    # Input files uploaded, and output files or charts saved, per call.
    sandbox_max_files: int = Field(10, ge=1, validation_alias="SANDBOX_MAX_FILES")
    # Output one call may stream back before it is stopped; bounds server memory.
    sandbox_max_stream_chars: int = Field(
        5_000_000, ge=1, validation_alias="SANDBOX_MAX_STREAM_CHARS"
    )
    # --- The user's files (api/services/files): Files page and agent artifacts --
    # Everything one user keeps, uploads and agent artifacts together.
    workspace_max_total_bytes: int = Field(
        100_000_000, ge=1, validation_alias="WORKSPACE_MAX_TOTAL_BYTES"
    )
    # What the Files page accepts; each upload is capped at DOCUMENT_MAX_BYTES.
    workspace_upload_extensions: CommaList = Field(
        [
            ".pdf",
            ".docx",
            ".xlsx",
            ".pptx",
            ".txt",
            ".md",
            ".csv",
            ".json",
            ".yaml",
            ".yml",
            ".html",
        ],
        validation_alias="WORKSPACE_UPLOAD_EXTENSIONS",
    )
    # TrueType fonts for PDF artifacts, so non-Latin text prints. Without them
    # PDFs use a built-in font that covers Western European text only.
    pdf_font_path: Path = Field(
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"), validation_alias="PDF_FONT_PATH"
    )
    pdf_bold_font_path: Path = Field(
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        validation_alias="PDF_BOLD_FONT_PATH",
    )
    # --- Documents attached to a pipeline run (api/services/documents) --------
    # An upload is read into memory, so each of these bounds a different cost.
    document_max_bytes: int = Field(10_000_000, ge=1, validation_alias="DOCUMENT_MAX_BYTES")
    # Text kept from one document; the rest is dropped and the run is told so.
    document_max_chars: int = Field(120_000, ge=1, validation_alias="DOCUMENT_MAX_CHARS")
    document_max_pages: int = Field(300, ge=1, validation_alias="DOCUMENT_MAX_PAGES")
    # .docx, .xlsx and .pptx are zips: refuse one that would unpack to more than this.
    document_max_unpacked_bytes: int = Field(
        50_000_000, ge=1, validation_alias="DOCUMENT_MAX_UNPACKED_BYTES"
    )
    # Refuse an image (or cap a rendered PDF page) past this size, before decoding it.
    document_max_image_pixels: int = Field(
        40_000_000, ge=1, validation_alias="DOCUMENT_MAX_IMAGE_PIXELS"
    )
    # Rows read from one .xlsx workbook, across all its sheets.
    document_max_spreadsheet_rows: int = Field(
        5_000, ge=1, validation_alias="DOCUMENT_MAX_SPREADSHEET_ROWS"
    )
    # OCR for scanned PDFs and images (Tesseract; api/services/documents/ocr.py).
    document_ocr_enabled: bool = Field(True, validation_alias="DOCUMENT_OCR_ENABLED")
    document_ocr_languages: str = Field(
        "eng+fra",
        pattern=r"^[A-Za-z0-9_]+(\+[A-Za-z0-9_]+)*$",
        validation_alias="DOCUMENT_OCR_LANGUAGES",
    )
    document_ocr_max_pages: int = Field(30, ge=1, validation_alias="DOCUMENT_OCR_MAX_PAGES")
    document_ocr_timeout_seconds: float = Field(
        15.0, gt=0, validation_alias="DOCUMENT_OCR_TIMEOUT_SECONDS"
    )
    document_ocr_dpi: int = Field(300, ge=72, validation_alias="DOCUMENT_OCR_DPI")
    # Upper bound on provider calls one pipeline run makes at once for a stage
    # whose steps run in parallel.
    pipeline_max_parallel_steps: int = Field(
        4, ge=1, validation_alias="PIPELINE_MAX_PARALLEL_STEPS"
    )
    # --- Background runs (api/services/runs.py) -------------------------------
    # Runs executing at once in this process; the others wait, queued.
    run_max_concurrent: int = Field(4, ge=1, validation_alias="RUN_MAX_CONCURRENT")
    # On shutdown, how long active runs get to record that they were interrupted.
    run_shutdown_grace_seconds: float = Field(
        5.0, gt=0, validation_alias="RUN_SHUTDOWN_GRACE_SECONDS"
    )
    # A run stops once its model calls cost this much (USD), unless the person
    # starting it sets their own limit. Empty (None): no limit.
    run_default_max_cost_usd: float | None = Field(
        None, gt=0, allow_inf_nan=False, validation_alias="RUN_DEFAULT_MAX_COST_USD"
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

    @field_validator(
        "allowed_hosts",
        "cors_allowed_origins",
        "agent_builtin_tools",
        "agent_approval_tools",
        "workspace_upload_extensions",
        mode="before",
    )
    @classmethod
    def _split_commas(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("workspace_upload_extensions", mode="after")
    @classmethod
    def _dotted_lowercase(cls, value: list[str]) -> list[str]:
        """``PDF`` and ``.pdf`` both mean ``.pdf``."""
        return [f".{item.lower().lstrip('.')}" for item in value]

    @field_validator(
        "openrouter_api_key",
        "togetherai_api_key",
        "tavily_api_key",
        "e2b_api_key",
        "secret_key",
        mode="after",
    )
    @classmethod
    def _drop_placeholders(cls, value: str) -> str:
        value = value.strip()
        return "" if value.lower() in SECRET_PLACEHOLDERS else value

    @field_validator("log_level", mode="after")
    @classmethod
    def _upper(cls, value: str) -> str:
        return value.upper()

    @field_validator("run_default_max_cost_usd", mode="before")
    @classmethod
    def _empty_is_unset(cls, value: object) -> object:
        """``RUN_DEFAULT_MAX_COST_USD=`` (empty) means no limit."""
        return None if isinstance(value, str) and not value.strip() else value

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
            if self.integrations_allow_private_network:
                raise ValueError("INTEGRATIONS_ALLOW_PRIVATE_NETWORK must be false in production.")
        elif not self.secret_key:
            self.secret_key = LOCAL_SECRET_KEY
        return self

    @property
    def max_request_bytes(self) -> int:
        """Largest request body accepted: one upload plus multipart overhead.

        DOCUMENT_MAX_BYTES caps every uploaded file, a run document or a file for
        the Files page alike, so this one number bounds both endpoints."""
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
