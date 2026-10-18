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
    WEB_SEARCH,
    calculator_tool,
    current_datetime_tool,
    fetch_url_tool,
    web_search_tool,
)
from api.services.toolbox.web import WebGateway

ToolBuilder = Callable[[ToolboxConfig], BaseTool | None]


def _web_search(config: ToolboxConfig) -> BaseTool | None:
    return web_search_tool(WebGateway(config)) if config.search_api_key else None


TOOLBOX: dict[str, ToolBuilder] = {
    WEB_SEARCH: _web_search,
    FETCH_URL: lambda config: fetch_url_tool(WebGateway(config)),
    CALCULATOR: lambda config: calculator_tool(),
    CURRENT_DATETIME: lambda config: current_datetime_tool(),
}


def toolbox_tools(config: ToolboxConfig) -> list[BaseTool]:
    """The enabled and configured built-in tools, in registry order."""
    built = (build(config) for name, build in TOOLBOX.items() if name in config.enabled)
    return [item for item in built if item is not None]
