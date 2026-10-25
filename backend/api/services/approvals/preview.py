"""A tool call's arguments as the run's owner reads them: JSON within a size limit.

The model chooses the arguments, so they can be any size. ``preview_arguments``
keeps their structure and cuts only what does not fit: long text values are
shortened (marked with an ellipsis), by as much as needed for the whole to stay
within APPROVAL_ARGUMENTS_MAX_CHARS. If even that is not enough (thousands of
keys), the start of the JSON text is kept instead. Never logged (AGENTS.md §6).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

ELLIPSIS = "…"
#: The shortest a text value is cut to before the whole is cut instead.
MIN_VALUE_CHARS = 40
#: Key of the fallback object that holds the start of the arguments' JSON text.
CUT_KEY = "arguments"


def _text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _shorten(value: Any, cap: int) -> Any:
    """``value`` with every text longer than ``cap`` cut to ``cap`` characters."""
    if isinstance(value, str):
        return value if len(value) <= cap else value[:cap] + ELLIPSIS
    if isinstance(value, Mapping):
        return {str(key): _shorten(item, cap) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_shorten(item, cap) for item in value]
    return value


def preview_arguments(arguments: Mapping[str, Any], max_chars: int) -> tuple[dict[str, Any], bool]:
    """The call's arguments as plain JSON values for display, and whether any
    of it was cut to fit ``max_chars``."""
    value: dict[str, Any] = json.loads(_text(arguments))
    if len(_text(value)) <= max_chars:
        return value, False
    cap = max_chars // 2
    while cap >= MIN_VALUE_CHARS:
        shortened = _shorten(value, cap)
        if len(_text(shortened)) <= max_chars:
            return shortened, True
        cap //= 2
    return {CUT_KEY: _text(value)[:max_chars] + ELLIPSIS}, True
