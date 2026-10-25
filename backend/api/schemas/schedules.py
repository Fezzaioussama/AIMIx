"""Contracts for scheduled runs: when a schedule runs, what each run is given,
and the schedule as the API shows it."""

from __future__ import annotations

from datetime import time
from typing import Annotated

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from api.models import TIMEZONE_MAX_LENGTH, RunStatus, ScheduleFrequency
from api.schemas.common import RunInputValues, Trimmed, UtcDateTime, ensure_run_input_size
from api.schemas.pipelines import PipelineInputField, RunRequest
from api.services.schedules.timing import time_zone_error


def _known_zone(name: str) -> str:
    if error := time_zone_error(name):
        raise ValueError(error)
    return name


def _clock_text(value: object) -> object:
    """A stored ``time`` as "HH:MM"."""
    return value.strftime("%H:%M") if isinstance(value, time) else value


def _none_if_empty(value: object) -> object:
    return value or None


#: "HH:MM" on a 24-hour clock, e.g. "09:00".
ClockTime = Annotated[str, StringConstraints(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")]
#: An IANA time zone name this server knows, e.g. "Europe/Paris".
TimeZoneName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=TIMEZONE_MAX_LENGTH),
    AfterValidator(_known_zone),
]
#: 0 is Monday, 6 Sunday.
Weekday = Annotated[int, Field(ge=0, le=6)]
#: Past the end of a shorter month, its last day.
DayOfMonth = Annotated[int, Field(ge=1, le=31)]


def clock_time(text: str) -> time:
    """A validated "HH:MM" as a ``time``."""
    hours, minutes = text.split(":")
    return time(int(hours), int(minutes))


class ScheduleTimingIn(BaseModel):
    """When a schedule runs. Also the body of POST /api/schedules/preview."""

    frequency: ScheduleFrequency
    #: In ``timezone``; an hourly schedule uses the minutes only.
    time: ClockTime
    #: Weekly schedules only.
    weekday: Weekday | None = None
    #: Monthly schedules only.
    day_of_month: DayOfMonth | None = None
    timezone: TimeZoneName


class ScheduleIn(ScheduleTimingIn, RunRequest):
    """Body of POST /api/schedules: a pipeline, its timing, and what each run
    is given (``input`` or ``inputs``, as for a run)."""

    pipeline_id: int
    enabled: bool = True


class SchedulePatch(BaseModel):
    """Body of PATCH /api/schedules/{id}: omitted fields keep their value.

    Timing fields are changed one by one. ``input`` and ``inputs`` replace what
    each run is given as a whole: the one left out becomes empty."""

    frequency: ScheduleFrequency | None = None
    time: ClockTime | None = None
    weekday: Weekday | None = None
    day_of_month: DayOfMonth | None = None
    timezone: TimeZoneName | None = None
    input: Trimmed | None = None
    inputs: RunInputValues | None = None
    enabled: bool | None = None

    @model_validator(mode="after")
    def _bounded(self) -> SchedulePatch:
        ensure_run_input_size(self.input, self.inputs)
        return self


class ScheduleListQuery(BaseModel):
    """Query of GET /api/schedules: optionally one pipeline's schedules only."""

    pipeline_id: int | None = None


class LastRunOut(BaseModel):
    """The newest run a schedule started (by itself or with "run now")."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    status: RunStatus
    created_at: UtcDateTime


class ScheduleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    pipeline_id: int
    pipeline_name: str
    #: The named inputs the pipeline declares, for editing ``inputs``.
    pipeline_inputs: list[PipelineInputField]
    frequency: ScheduleFrequency
    time: Annotated[str, BeforeValidator(_clock_text)] = Field(validation_alias="at")
    weekday: int | None
    day_of_month: int | None
    timezone: str
    input: str = Field(validation_alias="input_text")
    inputs: dict[str, str] = Field(validation_alias="input_values")
    enabled: bool
    #: Null while the schedule is off.
    next_run_at: UtcDateTime | None
    last_run: LastRunOut | None
    #: Why its latest time could not start a run; null when it did.
    last_error: Annotated[str | None, BeforeValidator(_none_if_empty)]
    created_at: UtcDateTime


class SchedulePreviewOut(BaseModel):
    """When a schedule with this timing would run first, from now."""

    next_run_at: UtcDateTime
