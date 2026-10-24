"""Built-in tool registry: name -> builder (AGENTS.md §7 Strategy + Registry).

Adding a tool is a new entry, never a new branch. AGENT_BUILTIN_TOOLS picks the
entries on offer (unknown names are ignored); a builder returns None when its
tool is not configured, so the catalogue never lists a tool that cannot work.
"""

from __future__ import annotations

from collections.abc import Callable

from langchain_core.tools import BaseTool

from api.services.toolbox.config import ToolboxConfig
from api.services.toolbox.tools import (
    CALCULATOR,
    CURRENT_DATETIME,
    FETCH_URL,
    LIST_WORKSPACE_FILES,
    READ_CSV,
    READ_WORKSPACE_FILE,
    SAVE_ARTIFACT,
    SEARCH_WORKSPACE_FILES,
    WEB_SEARCH,
    calculator_tool,
    current_datetime_tool,
    fetch_url_tool,
    list_workspace_files_tool,
    read_csv_tool,
    read_workspace_file_tool,
    save_artifact_tool,
    search_workspace_files_tool,
    web_search_tool,
)
from api.services.toolbox.web import WebGateway
from api.services.toolbox.workspace import LocalWorkspace, WorkspaceLimits

ToolBuilder = Callable[[ToolboxConfig], BaseTool | None]


def _web_search(config: ToolboxConfig) -> BaseTool | None:
    return web_search_tool(WebGateway(config)) if config.search_api_key else None


def _workspace(config: ToolboxConfig) -> LocalWorkspace | None:
    if not config.workspace_dir.is_dir():
        return None
    limits = WorkspaceLimits(
        config.workspace_max_file_bytes,
        config.workspace_max_output_chars,
        config.workspace_search_max_files,
        config.workspace_search_max_results,
        config.workspace_csv_max_rows,
    )
    return LocalWorkspace(config.workspace_dir, limits)


def _workspace_tool(
    config: ToolboxConfig, builder: Callable[[LocalWorkspace], BaseTool]
) -> BaseTool | None:
    workspace = _workspace(config)
    return builder(workspace) if workspace else None


TOOLBOX: dict[str, ToolBuilder] = {
    WEB_SEARCH: _web_search,
    FETCH_URL: lambda config: fetch_url_tool(WebGateway(config)),
    CALCULATOR: lambda config: calculator_tool(),
    CURRENT_DATETIME: lambda config: current_datetime_tool(),
    LIST_WORKSPACE_FILES: lambda config: _workspace_tool(config, list_workspace_files_tool),
    READ_WORKSPACE_FILE: lambda config: _workspace_tool(config, read_workspace_file_tool),
    SEARCH_WORKSPACE_FILES: lambda config: _workspace_tool(config, search_workspace_files_tool),
    READ_CSV: lambda config: _workspace_tool(config, read_csv_tool),
    SAVE_ARTIFACT: lambda config: _workspace_tool(config, save_artifact_tool),
}


def toolbox_tools(config: ToolboxConfig) -> list[BaseTool]:
    """The enabled and configured built-in tools, in registry order."""
    built = (build(config) for name, build in TOOLBOX.items() if name in config.enabled)
    return [item for item in built if item is not None]
