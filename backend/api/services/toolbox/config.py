"""Toolbox configuration, copied out of the settings once (AGENTS.md §5 D)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from api.services.documents.contracts import ExtractionLimits
from api.services.documents.extraction import extraction_limits
from config.settings import Settings


@dataclass(frozen=True)
class ToolboxConfig:
    """Limits and credentials the built-in tools need (§7 Value Object).

    An empty ``search_api_key`` means web search is not configured.
    An empty ``sandbox_api_key`` means run_python is not configured.
    """

    enabled: tuple[str, ...]
    timeout_seconds: float
    fetch_max_bytes: int
    fetch_max_chars: int
    search_url: str
    search_max_results: int
    workspace_dir: Path
    workspace_max_file_bytes: int
    workspace_max_output_chars: int
    workspace_search_max_files: int
    workspace_search_max_results: int
    workspace_csv_max_rows: int
    allow_workspace_network_access: bool
    sandbox_timeout_seconds: float
    sandbox_max_output_chars: int
    sandbox_max_files: int
    sandbox_max_stream_chars: int
    workspace_max_total_bytes: int
    #: What reading a PDF or Word file from the workspace may cost.
    document_limits: ExtractionLimits
    pdf_font_path: Path
    pdf_bold_font_path: Path
    # Kept out of repr, so a logged config never shows it.
    search_api_key: str = field(default="", repr=False)
    sandbox_api_key: str = field(default="", repr=False)


def toolbox_config(settings: Settings, workspace_dir: Path | None = None) -> ToolboxConfig:
    return ToolboxConfig(
        enabled=tuple(settings.agent_builtin_tools),
        timeout_seconds=settings.web_timeout_seconds,
        fetch_max_bytes=settings.web_fetch_max_bytes,
        fetch_max_chars=settings.web_fetch_max_chars,
        search_url=settings.tavily_search_url,
        search_max_results=settings.web_search_max_results,
        workspace_dir=workspace_dir or settings.workspace_dir,
        workspace_max_file_bytes=settings.workspace_max_file_bytes,
        workspace_max_output_chars=settings.workspace_max_output_chars,
        workspace_search_max_files=settings.workspace_search_max_files,
        workspace_search_max_results=settings.workspace_search_max_results,
        workspace_csv_max_rows=settings.workspace_csv_max_rows,
        allow_workspace_network_access=settings.agent_allow_workspace_network_access,
        sandbox_timeout_seconds=settings.sandbox_timeout_seconds,
        sandbox_max_output_chars=settings.sandbox_max_output_chars,
        sandbox_max_files=settings.sandbox_max_files,
        sandbox_max_stream_chars=settings.sandbox_max_stream_chars,
        workspace_max_total_bytes=settings.workspace_max_total_bytes,
        document_limits=extraction_limits(settings),
        pdf_font_path=settings.pdf_font_path,
        pdf_bold_font_path=settings.pdf_bold_font_path,
        search_api_key=settings.tavily_api_key,
        sandbox_api_key=settings.e2b_api_key,
    )
