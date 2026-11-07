"""What a tool call was about, in a few words, for a run's trace: the search query,
the page's address, the file's path, the question. Kept with each call's name and
status (``ToolCallTrace.target``), so the report can say what an agent looked at,
never the tool's output. One entry per built-in tool names the argument that says
it (Strategy + Registry, §5 O); any other tool shows its first text argument, and
``NOTHING`` keeps a tool's arguments out of the trace altogether."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

#: The most of an argument's text a trace keeps.
TARGET_MAX_CHARS = 120
#: A tool whose arguments are not a subject (run_python's code can hold anything).
NOTHING = ""
#: Any tool not listed: its first text argument.
FIRST_TEXT = "*"

#: Which argument says what a built-in tool's call is about.
TARGET_ARGUMENTS: dict[str, str] = {
    "web_search": "query",
    "fetch_url": "url",
    "read_workspace_file": "path",
    "search_workspace_files": "query",
    "read_csv": "path",
    "save_artifact": "path",
    "generate_image": "path",
    "find_objects": "what",
    "ask_user": "question",
    "run_python": NOTHING,
    "calculator": "expression",
}


def _cut(text: str) -> str:
    return text if len(text) <= TARGET_MAX_CHARS else f"{text[: TARGET_MAX_CHARS - 1]}…"


def call_target(name: str, arguments: Mapping[str, Any]) -> str:
    """The call's subject, cut to TARGET_MAX_CHARS; "" when it has none."""
    key = TARGET_ARGUMENTS.get(name, FIRST_TEXT)
    if key == NOTHING:
        return ""
    if key == FIRST_TEXT:
        value = next((item for item in arguments.values() if isinstance(item, str)), "")
    else:
        value = arguments.get(key, "")
    return _cut(value.strip()) if isinstance(value, str) else ""
