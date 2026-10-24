"""LangChain tools over the toolbox helpers (AGENTS.md §7 Adapter).

Every tool sets ``handle_tool_error``: a ``ToolException`` reaches the model as
an error result it can react to, and the run's trace records the call as
"error", instead of the failure aborting the agent.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

from langchain_core.tools import BaseTool, StructuredTool

from api.services.toolbox.calculator import evaluate
from api.services.toolbox.web import WebGateway
from api.services.toolbox.workspace import LocalWorkspace

#: Tool names: the keys of the registry and of AGENT_BUILTIN_TOOLS.
WEB_SEARCH = "web_search"
FETCH_URL = "fetch_url"
CALCULATOR = "calculator"
CURRENT_DATETIME = "current_datetime"
LIST_WORKSPACE_FILES = "list_workspace_files"
READ_WORKSPACE_FILE = "read_workspace_file"
SEARCH_WORKSPACE_FILES = "search_workspace_files"
READ_CSV = "read_csv"
SAVE_ARTIFACT = "save_artifact"

TRUNCATED_NOTE = "\n\n[Truncated: the page continues beyond this point.]"


def make_tool(
    name: str,
    description: str,
    func: Callable[..., str] | None = None,
    coroutine: Callable[..., Awaitable[str]] | None = None,
) -> BaseTool:
    return StructuredTool.from_function(
        func=func,
        coroutine=coroutine,
        name=name,
        description=description,
        handle_tool_error=True,
    )


def web_search_tool(gateway: WebGateway) -> BaseTool:
    async def web_search(query: str) -> str:
        hits = await gateway.search(query)
        if not hits:
            return "No results."
        return "\n\n".join(
            f"{number}. {hit.title}\nURL: {hit.url}\n{hit.snippet}"
            for number, hit in enumerate(hits, start=1)
        )

    return make_tool(
        WEB_SEARCH,
        "Search the web for current information. Returns the top results with their "
        "title, URL and a snippet; use fetch_url on a result to read the whole page.",
        coroutine=web_search,
    )


def fetch_url_tool(gateway: WebGateway) -> BaseTool:
    async def fetch_url(url: str) -> str:
        page = await gateway.fetch(url)
        text = page.text or "The page has no readable text."
        return f"URL: {page.url}\n\n{text}{TRUNCATED_NOTE if page.truncated else ''}"

    return make_tool(
        FETCH_URL,
        "Read a public web page (an http or https URL) and return its text content.",
        coroutine=fetch_url,
    )


def calculator_tool() -> BaseTool:
    def calculator(expression: str) -> str:
        return str(evaluate(expression))

    return make_tool(
        CALCULATOR,
        "Evaluate an arithmetic expression reliably, e.g. '(1250 * 0.07) / 12' or "
        "'sqrt(2) * pi'. Supports + - * / // % **, parentheses, abs, round, sqrt, exp, "
        "log, log10, sin, cos, tan, floor, ceil, pi and e.",
        func=calculator,
    )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def current_datetime_tool(clock: Callable[[], datetime] = _utc_now) -> BaseTool:
    def current_datetime() -> str:
        now = clock()
        return f"{now.isoformat(timespec='seconds')} ({now:%A})"

    return make_tool(
        CURRENT_DATETIME,
        "Return the current date and time in UTC (ISO 8601) and the weekday.",
        func=current_datetime,
    )


def list_workspace_files_tool(workspace: LocalWorkspace) -> BaseTool:
    return make_tool(
        LIST_WORKSPACE_FILES,
        "List visible files in the configured local workspace or one of its subdirectories.",
        func=workspace.list_files,
    )


def read_workspace_file_tool(workspace: LocalWorkspace) -> BaseTool:
    return make_tool(
        READ_WORKSPACE_FILE,
        "Read a bounded UTF-8 text, Markdown, JSON, YAML, HTML, or CSV file from the local "
        "workspace.",
        func=workspace.read_file,
    )


def search_workspace_files_tool(workspace: LocalWorkspace) -> BaseTool:
    return make_tool(
        SEARCH_WORKSPACE_FILES,
        "Search visible text files in the local workspace and return matching paths and lines.",
        func=workspace.search_files,
    )


def read_csv_tool(workspace: LocalWorkspace) -> BaseTool:
    return make_tool(
        READ_CSV,
        "Read a local workspace CSV file as structured JSON rows for analysis.",
        func=workspace.read_csv,
    )


def save_artifact_tool(workspace: LocalWorkspace) -> BaseTool:
    return make_tool(
        SAVE_ARTIFACT,
        "Save a new text, Markdown, JSON, or CSV deliverable inside the local workspace. "
        "Existing files are never overwritten.",
        func=workspace.save_artifact,
    )
