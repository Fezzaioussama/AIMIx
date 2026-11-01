"""The events a chat reply streams to the client, one JSON object per line.

The stream carries the assistant's text and the tools it used, so the chat screen
can show what the agent is doing and offer a link to what it created instead of
only printing a sentence (AGENTS.md §6 explicit contracts).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Literal

ChatEventKind = Literal["text", "tool"]
ToolStatus = Literal["started", "finished", "failed"]
ActionKind = Literal["pipeline", "schedule"]


@dataclass(frozen=True)
class ChatEvent:
    kind: ChatEventKind
    text: str = ""
    tool: str = ""
    label: str = ""
    status: ToolStatus = "started"
    detail: str = ""
    action: dict[str, Any] | None = None


def text_event(text: str) -> ChatEvent:
    return ChatEvent("text", text=text)


def tool_started(name: str) -> ChatEvent:
    return ChatEvent("tool", tool=name, label=tool_label(name), status="started")


def tool_finished(name: str, output: object) -> ChatEvent:
    action = action_for(name, output)
    detail = action["subtitle"] if action else ""
    return ChatEvent(
        "tool",
        tool=name,
        label=tool_label(name),
        status="finished",
        detail=detail,
        action=action,
    )


def tool_failed(name: str, detail: str) -> ChatEvent:
    return ChatEvent("tool", tool=name, label=tool_label(name), status="failed", detail=detail)


def encode(event: ChatEvent) -> str:
    """One NDJSON line; empty fields are left out of the object."""
    payload: dict[str, Any] = {"type": event.kind}
    if event.kind == "text":
        payload["text"] = event.text
    else:
        payload.update(tool=event.tool, label=event.label, status=event.status)
        if event.detail:
            payload["detail"] = event.detail
        if event.action:
            payload["action"] = event.action
    return json.dumps(payload, ensure_ascii=False) + "\n"


#: What the agent is doing, in the words the chat shows while a tool runs.
TOOL_LABELS: dict[str, str] = {
    "list_pipelines": "Listing your pipelines",
    "inspect_pipeline": "Inspecting a pipeline",
    "create_pipeline": "Creating a pipeline",
    "update_pipeline": "Updating a pipeline",
    "run_pipeline": "Running a pipeline",
    "list_schedules": "Listing your schedules",
    "create_schedule": "Creating a schedule",
    "update_schedule": "Updating a schedule",
}

#: Which tools create a thing the screen can link to, and what that thing is.
ACTION_KINDS: dict[str, ActionKind] = {
    "create_pipeline": "pipeline",
    "update_pipeline": "pipeline",
    "create_schedule": "schedule",
    "update_schedule": "schedule",
}


def tool_label(name: str) -> str:
    """A known tool's phrase, else its name in words ("save_artifact" → "save artifact")."""
    return TOOL_LABELS.get(name) or re.sub(r"[_]+", " ", name).strip()


def action_for(name: str, output: object) -> dict[str, Any] | None:
    """The resource a finished tool created or changed, for a link in the chat."""
    kind = ACTION_KINDS.get(name)
    if kind is None:
        return None
    payload = _object(output)
    if payload is None:
        return None
    identifier = payload.get("id")
    if not isinstance(identifier, int):
        return None
    if kind == "pipeline":
        return {
            "kind": kind,
            "id": identifier,
            "title": _text(payload.get("name"), "Pipeline"),
            "subtitle": "Open the mission",
        }
    return {
        "kind": kind,
        "id": identifier,
        "title": _text(payload.get("pipeline_name"), "Schedule"),
        "subtitle": schedule_subtitle(payload),
    }


WEEKDAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def schedule_subtitle(payload: dict[str, Any]) -> str:
    """When a schedule runs as people read it ("Every Monday at 09:00", "Off")."""
    if payload.get("enabled") is False:
        return "Off"
    frequency = _text(payload.get("frequency"), "")
    at = _text(payload.get("time"), "")
    timezone = _text(payload.get("timezone"), "")
    if not frequency or not at:
        return "Schedule saved"
    words = timing_words(frequency, at, payload.get("weekday"), payload.get("day_of_month"))
    return words + (f" ({timezone})" if timezone else "")


def timing_words(frequency: str, at: str, weekday: object, day_of_month: object) -> str:
    """A frequency and clock time as a sentence ("Every Monday at 09:00")."""
    if frequency == "hourly":
        minutes = int(at.split(":")[1])
        return "Every hour, on the hour" if minutes == 0 else f"Every hour, {minutes} minutes past"
    if frequency == "weekly" and isinstance(weekday, int) and 0 <= weekday < len(WEEKDAY_NAMES):
        return f"Every {WEEKDAY_NAMES[weekday]} at {at}"
    if frequency == "monthly" and isinstance(day_of_month, int):
        return f"On the {_ordinal(day_of_month)} of every month at {at}"
    if frequency == "weekdays":
        return f"Every weekday at {at}"
    if frequency == "daily":
        return f"Every day at {at}"
    return f"{frequency.capitalize()} at {at}"


def _ordinal(day: int) -> str:
    suffix = "th" if 11 <= day % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return f"{day}{suffix}"


def _object(output: object) -> dict[str, Any] | None:
    """A tool's structured result; a ToolMessage or JSON text is decoded too."""
    content = getattr(output, "content", output)
    if isinstance(content, dict):
        return content
    if isinstance(content, str):
        try:
            decoded = json.loads(content)
        except json.JSONDecodeError:
            return None
        return decoded if isinstance(decoded, dict) else None
    return None


def _text(value: object, fallback: str) -> str:
    return value if isinstance(value, str) and value else fallback
