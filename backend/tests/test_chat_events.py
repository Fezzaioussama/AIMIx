"""The events a chat reply streams, and the links they carry."""

from __future__ import annotations

import json

from api.services.chat_events import (
    encode,
    text_event,
    tool_failed,
    tool_finished,
    tool_started,
)


def test_text_events_encode_as_one_json_line() -> None:
    assert encode(text_event("Hello")) == '{"type": "text", "text": "Hello"}\n'


def test_tool_events_carry_their_phrase_and_status() -> None:
    started = json.loads(encode(tool_started("create_schedule")))
    assert started == {
        "type": "tool",
        "tool": "create_schedule",
        "label": "Creating a schedule",
        "status": "started",
    }
    failed = json.loads(encode(tool_failed("create_schedule", "Bad timing")))
    assert failed["status"] == "failed"
    assert failed["detail"] == "Bad timing"


def test_a_finished_pipeline_tool_offers_a_mission_link() -> None:
    event = tool_finished("create_pipeline", {"id": 4, "name": "Weekly digest"})
    assert event.action == {
        "kind": "pipeline",
        "id": 4,
        "title": "Weekly digest",
        "subtitle": "Open the mission",
    }


def test_a_finished_schedule_tool_offers_a_schedule_link() -> None:
    event = tool_finished(
        "create_schedule",
        {
            "id": 7,
            "pipeline_name": "Weekly digest",
            "frequency": "daily",
            "time": "09:00",
            "timezone": "Europe/Paris",
            "enabled": True,
        },
    )
    assert event.action == {
        "kind": "schedule",
        "id": 7,
        "title": "Weekly digest",
        "subtitle": "Every day at 09:00 (Europe/Paris)",
    }


def test_a_weekly_schedule_names_its_weekday() -> None:
    event = tool_finished(
        "create_schedule",
        {
            "id": 8,
            "pipeline_name": "Weekly digest",
            "frequency": "weekly",
            "time": "09:00",
            "timezone": "Europe/Paris",
            "weekday": 0,
            "enabled": True,
        },
    )
    assert event.action is not None
    assert event.action["subtitle"] == "Every Monday at 09:00 (Europe/Paris)"


def test_a_read_only_tool_has_no_action() -> None:
    assert tool_finished("list_pipelines", [{"id": 1}]).action is None
