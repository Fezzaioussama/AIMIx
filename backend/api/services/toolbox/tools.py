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
from api.services.toolbox.code_runner import OUTPUT_FOLDER, CodeRunner
from api.services.toolbox.images import ImageStudio
from api.services.toolbox.sandbox import INPUT_DIR, OUTPUT_DIR
from api.services.toolbox.vision import ObjectSpotter
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
RUN_PYTHON = "run_python"
GENERATE_IMAGE = "generate_image"
FIND_OBJECTS = "find_objects"

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
        "List the files in the user's workspace or one of its folders: files the user "
        "uploaded and artifacts saved earlier.",
        func=workspace.list_files,
    )


def read_workspace_file_tool(workspace: LocalWorkspace) -> BaseTool:
    return make_tool(
        READ_WORKSPACE_FILE,
        "Read a file from the user's workspace: text, Markdown, JSON, YAML, HTML and CSV "
        "as written, PDF and Word files as their text. The output is bounded.",
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
        "Save a new file in the user's workspace; they can download it from their Files "
        "page. The extension sets the format: .txt, .md, .json, .csv or .html are saved as "
        "written. For .docx or .pdf, write Markdown (headings, lists, bold, italic, tables): "
        "it becomes a formatted document; a line holding only ![description](path) shows "
        "that PNG or JPEG of the workspace. Never overwrites.",
        func=workspace.save_artifact,
    )


def generate_image_tool(studio: ImageStudio) -> BaseTool:
    return make_tool(
        GENERATE_IMAGE,
        "Draw a picture with Meta's Muse Image model and save it as a new JPEG in the user's "
        "workspace (they see it on their Files page). description: the subject, style, "
        "colours, composition and any text to show, in detail. path: e.g. "
        "images/launch-hero.jpg. shape: square, landscape or portrait. Each picture costs "
        "money: draw only the ones the task needs.",
        func=studio.create,
    )


def find_objects_tool(spotter: ObjectSpotter) -> BaseTool:
    return make_tool(
        FIND_OBJECTS,
        "Find and count every object of one kind in a PNG or JPEG picture of the user's "
        "workspace with Meta's SAM 3.1 vision model. what: a short noun phrase naming one "
        "kind of thing, e.g. 'loaf of bread' or 'scratch'. Returns how many it found, with "
        "a box and a confidence for each, and saves a copy of the picture with the boxes "
        "numbered, ready for a report.",
        func=spotter.find,
    )


def run_python_tool(runner: CodeRunner) -> BaseTool:
    return make_tool(
        RUN_PYTHON,
        "Run Python in a fresh sandbox without internet; returns stdout, stderr, the final "
        f"result and any error. input_files are copied from the workspace to {INPUT_DIR}/"
        f"<path>; files written to {OUTPUT_DIR}/ and displayed PNG charts are saved to the "
        f"workspace under {OUTPUT_FOLDER}/<UTC time>/.",
        coroutine=runner.run,
    )
