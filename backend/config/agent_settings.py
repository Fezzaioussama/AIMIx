"""Settings of the agents: MCP, approval gates, integrations and built-in tools."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator

from config.fields import BASE_DIR, CommaList, Secret


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


class AgentSettings(BaseModel):
    agent_timeout_seconds: float = Field(3600.0, gt=0, validation_alias="AGENT_TIMEOUT_SECONDS")
    agent_recursion_limit: int = Field(25, ge=2, validation_alias="AGENT_RECURSION_LIMIT")
    agent_tool_description_max_chars: int = Field(
        300, ge=1, validation_alias="AGENT_TOOL_DESCRIPTION_MAX_CHARS"
    )
    mcp_timeout_seconds: float = Field(30.0, gt=0, validation_alias="MCP_TIMEOUT_SECONDS")
    mcp_servers: dict[str, MCPServer] = Field(default_factory=dict, validation_alias="MCP_SERVERS")
    # One HTTP response from a user's MCP server (a JSON answer or an event
    # stream) is cut off past this many bytes, so it cannot fill the memory.
    mcp_max_response_bytes: int = Field(10_000_000, ge=1, validation_alias="MCP_MAX_RESPONSE_BYTES")
    # The text of one MCP tool result the model receives is cut here.
    mcp_tool_result_max_chars: int = Field(
        50_000, ge=1, validation_alias="MCP_TOOL_RESULT_MAX_CHARS"
    )
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
            "generate_image",
            "find_objects",
        ],
        validation_alias="AGENT_BUILTIN_TOOLS",
    )
    # Explicit opt-in: otherwise file-reading tools suppress outbound web tools,
    # preventing model-driven disclosure of workspace data.
    agent_allow_workspace_network_access: bool = Field(
        False, validation_alias="AGENT_ALLOW_WORKSPACE_NETWORK_ACCESS"
    )
    web_timeout_seconds: float = Field(15.0, gt=0, validation_alias="WEB_TIMEOUT_SECONDS")
    # The whole of one fetch_url call, every redirect and the download included.
    web_fetch_max_seconds: float = Field(30.0, gt=0, validation_alias="WEB_FETCH_MAX_SECONDS")
    web_fetch_max_bytes: int = Field(2_000_000, ge=1, validation_alias="WEB_FETCH_MAX_BYTES")
    web_fetch_max_chars: int = Field(20_000, ge=1, validation_alias="WEB_FETCH_MAX_CHARS")
    web_search_max_results: int = Field(5, ge=1, le=20, validation_alias="WEB_SEARCH_MAX_RESULTS")
    tavily_api_key: Secret = Field("", validation_alias="TAVILY_API_KEY")
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
    e2b_api_key: Secret = Field("", validation_alias="E2B_API_KEY")
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
    # run_python calls one account may make per hour: each spends E2B_API_KEY.
    sandbox_max_calls_per_hour: int = Field(
        120, ge=1, validation_alias="SANDBOX_MAX_CALLS_PER_HOUR"
    )

    @field_validator("workspace_dir", mode="after")
    @classmethod
    def _workspace_path(cls, value: Path) -> Path:
        return value if value.is_absolute() else BASE_DIR / value
