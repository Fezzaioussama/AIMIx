"""Built-in tool registry: name -> builder (AGENTS.md §7 Strategy + Registry).

Adding a tool is a new entry, never a new branch. AGENT_BUILTIN_TOOLS picks the
entries on offer (unknown names are ignored); a builder returns None when its
tool is not configured, so the catalogue never lists a tool that cannot work.
"""

from __future__ import annotations

from collections.abc import Callable

from langchain_core.tools import BaseTool

from api.services.artifacts.contracts import RenderOptions
from api.services.files.storage import WorkspaceStorage
from api.services.toolbox.code_runner import CodeRunner
from api.services.toolbox.config import ToolboxConfig
from api.services.toolbox.e2b_sandbox import E2BSandboxOpener
from api.services.toolbox.sandbox import SandboxLimits, SandboxOpener, metered
from api.services.toolbox.tools import (
    CALCULATOR,
    CURRENT_DATETIME,
    FETCH_URL,
    LIST_WORKSPACE_FILES,
    READ_CSV,
    READ_WORKSPACE_FILE,
    RUN_PYTHON,
    SAVE_ARTIFACT,
    SEARCH_WORKSPACE_FILES,
    WEB_SEARCH,
    calculator_tool,
    current_datetime_tool,
    fetch_url_tool,
    list_workspace_files_tool,
    read_csv_tool,
    read_workspace_file_tool,
    run_python_tool,
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
    storage = WorkspaceStorage(
        config.workspace_dir, config.workspace_max_total_bytes, config.workspace_max_files
    )
    try:
        storage.prepare()
    except OSError:
        return None
    limits = WorkspaceLimits(
        config.workspace_max_file_bytes,
        config.workspace_max_output_chars,
        config.workspace_search_max_files,
        config.workspace_search_max_results,
        config.workspace_csv_max_rows,
        config.document_limits,
    )
    render = RenderOptions(config.pdf_font_path, config.pdf_bold_font_path)
    return LocalWorkspace(storage, limits, render)


def _workspace_tool(
    config: ToolboxConfig, builder: Callable[[LocalWorkspace], BaseTool]
) -> BaseTool | None:
    workspace = _workspace(config)
    return builder(workspace) if workspace else None


def _code_runner(workspace: LocalWorkspace, config: ToolboxConfig) -> CodeRunner:
    limits = SandboxLimits(
        timeout_seconds=config.sandbox_timeout_seconds,
        max_files=config.sandbox_max_files,
        max_file_bytes=config.workspace_max_file_bytes,
        max_output_chars=config.sandbox_max_output_chars,
    )
    opener: SandboxOpener = E2BSandboxOpener(
        config.sandbox_api_key, config.sandbox_timeout_seconds, config.sandbox_max_stream_chars
    )
    if config.sandbox_quota is not None:
        opener = metered(opener, config.sandbox_quota)
    return CodeRunner(opener, workspace, limits)


def _run_python(config: ToolboxConfig) -> BaseTool | None:
    """Offered only with an E2B key and a usable workspace."""
    workspace = _workspace(config) if config.sandbox_api_key else None
    return run_python_tool(_code_runner(workspace, config)) if workspace else None


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
    RUN_PYTHON: _run_python,
}

# run_python reads workspace files (its input_files), so it counts as a reader.
# It is not outbound: its sandbox has no internet access (e2b_sandbox.py).
WORKSPACE_READ_TOOLS = frozenset(
    {LIST_WORKSPACE_FILES, READ_WORKSPACE_FILE, SEARCH_WORKSPACE_FILES, READ_CSV, RUN_PYTHON}
)
OUTBOUND_TOOLS = frozenset({WEB_SEARCH, FETCH_URL})


def toolbox_tools(config: ToolboxConfig) -> list[BaseTool]:
    """The enabled and configured built-in tools, in registry order.

    Only readers actually offered remove the outbound tools: run_python without
    an E2B key reads nothing, so it must not take web search away.
    """
    enabled = set(config.enabled)
    built = (build(config) for name, build in TOOLBOX.items() if name in enabled)
    tools = [item for item in built if item is not None]
    readers = {item.name for item in tools} & WORKSPACE_READ_TOOLS
    if readers and not config.allow_workspace_network_access:
        return [item for item in tools if item.name not in OUTBOUND_TOOLS]
    return tools
