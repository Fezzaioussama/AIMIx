"""The schedule request contracts as service values.

Shared by the HTTP endpoint and the chat agent's schedule tools, so both accept
exactly the same input and apply the same rules (AGENTS.md §3).
"""

from __future__ import annotations

from datetime import time

from api.models import ScheduleFrequency
from api.schemas.schedules import ScheduleIn, SchedulePatch, ScheduleTimingIn
from api.services.runs import RunStart
from api.services.schedules.service import ScheduleDraft, ScheduleEdit, TimingEdit
from api.services.schedules.timing import Timing


def clock(text: str) -> time:
    """A validated "HH:MM" as a ``time``."""
    hours, minutes = text.split(":")
    return time(int(hours), int(minutes))


def timing(
    frequency: ScheduleFrequency,
    at: str,
    timezone: str,
    weekday: int | None = None,
    day_of_month: int | None = None,
) -> Timing:
    return Timing(frequency, timezone, clock(at), weekday, day_of_month)


def timing_of(body: ScheduleTimingIn) -> Timing:
    return timing(body.frequency, body.time, body.timezone, body.weekday, body.day_of_month)


def draft_of(body: ScheduleIn) -> ScheduleDraft:
    start = RunStart(body.input, body.inputs, body.budget)
    return ScheduleDraft(body.pipeline_id, timing_of(body), start, body.enabled)


def edit_of(body: SchedulePatch) -> ScheduleEdit:
    timing_edit = TimingEdit(
        frequency=body.frequency,
        at=None if body.time is None else clock(body.time),
        weekday=body.weekday,
        day_of_month=body.day_of_month,
        timezone=body.timezone,
    )
    sent_inputs = body.input is not None or body.inputs is not None
    start = RunStart(body.input or "", body.inputs or {}) if sent_inputs else None
    return ScheduleEdit(
        timing_edit, start, body.enabled, body.budget if body.sends_budget else None
    )
