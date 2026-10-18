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

#: Tool names: the keys of the registry and of AGENT_BUILTIN_TOOLS.
WEB_SEARCH = "web_search"
FETCH_URL = "fetch_url"
CALCULATOR = "calculator"
CURRENT_DATETIME = "current_datetime"

TRUNCATED_NOTE = "\n\n[Truncated: the page continues beyond this point.]"


def _tool(
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

    return _tool(
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

    return _tool(
        FETCH_URL,
        "Read a public web page (an http or https URL) and return its text content.",
        coroutine=fetch_url,
    )


def calculator_tool() -> BaseTool:
    def calculator(expression: str) -> str:
        return str(evaluate(expression))

    return _tool(
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

    return _tool(
        CURRENT_DATETIME,
        "Return the current date and time in UTC (ISO 8601) and the weekday.",
        func=current_datetime,
    )
