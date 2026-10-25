"""When a schedule runs next: its preset frequency, read on its time zone's clock.

Pure and clock-free: the caller says "after when". Each preset is one rule in
``FREQUENCIES`` (Strategy + Registry, AGENTS.md §5 O), so a new preset is a new
entry, never another branch.

A schedule's time is a wall-clock time in its IANA zone, so "every day at
09:00" stays at 09:00 across daylight-saving changes:

- the night the clocks go forward, a time in the skipped hour runs as much
  later as the clocks jumped (02:30 becomes 03:30);
- the night they go back, a time that happens twice runs once, the first time;
- an hourly schedule follows real hours: it runs every hour, both times
  through a repeated hour, and not in a skipped one;
- a monthly day past the end of a month (the 31st in April) is its last day.
"""

from __future__ import annotations

from calendar import monthrange
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from functools import cache
from typing import Protocol
from zoneinfo import ZoneInfo, available_timezones

from api.exceptions import ValidationFailed
from api.models import ScheduleFrequency

#: Every preset comes round within this many days; a monthly one on the 31st
#: just after a short month waits the longest.
_SEARCH_DAYS = 63
#: Wall-clock hours an hourly schedule looks ahead, a skipped hour included.
_SEARCH_HOURS = 3
#: Mondays to Fridays (``date.weekday()``: Monday is 0).
_WORKING_DAYS = range(5)


@dataclass(frozen=True)
class Timing:
    """When a schedule runs: a preset, a wall-clock time ``at`` in ``timezone``,
    and the day of the week (0 = Monday, weekly) or of the month (monthly)."""

    frequency: ScheduleFrequency
    timezone: str
    at: time = time(0, 0)
    weekday: int | None = None
    day_of_month: int | None = None


class Frequency(Protocol):
    """One preset: the optional fields it uses, and when it next comes round."""

    @property
    def uses(self) -> frozenset[str]: ...

    def next_after(self, timing: Timing, zone: ZoneInfo, after: datetime) -> datetime: ...


def _instant(wall: datetime, zone: ZoneInfo, fold: int = 0) -> datetime:
    """A wall-clock time on ``zone``'s clock as a UTC instant. ``fold`` 0 is the
    first pass through a repeated hour and 1 the second; in a skipped hour,
    fold 0 lands as much later as the clocks jumped."""
    return wall.replace(tzinfo=zone, fold=fold).astimezone(timezone.utc)


def _shown(moment: datetime, zone: ZoneInfo, wall: datetime) -> bool:
    """Whether ``zone``'s clock really shows ``wall`` at ``moment`` (it does
    not in a skipped hour)."""
    return moment.astimezone(zone).replace(tzinfo=None) == wall


@dataclass(frozen=True)
class _Hourly:
    """Every real hour, when the zone's clock shows the timing's minute."""

    uses: frozenset[str] = frozenset()

    def next_after(self, timing: Timing, zone: ZoneInfo, after: datetime) -> datetime:
        local = after.astimezone(zone).replace(tzinfo=None)
        start = local.replace(minute=timing.at.minute, second=0, microsecond=0)
        for hours in range(_SEARCH_HOURS + 1):
            wall = start + timedelta(hours=hours)
            for fold in (0, 1):
                moment = _instant(wall, zone, fold)
                if moment > after and _shown(moment, zone, wall):
                    return moment
        raise RuntimeError(f"No hourly time found after {after.isoformat()}.")


@dataclass(frozen=True)
class _OnDays:
    """Once on each day ``picks`` accepts, at the timing's wall-clock time."""

    picks: Callable[[date, Timing], bool]
    uses: frozenset[str] = field(default=frozenset({"hour"}))

    def next_after(self, timing: Timing, zone: ZoneInfo, after: datetime) -> datetime:
        today = after.astimezone(zone).date()
        for offset in range(_SEARCH_DAYS):
            day = today + timedelta(days=offset)
            if self.picks(day, timing):
                moment = _instant(datetime.combine(day, timing.at), zone)
                if moment > after:
                    return moment
        raise RuntimeError(f"No {timing.frequency.value} time found after {after.isoformat()}.")


def _every_day(_day: date, _timing: Timing) -> bool:
    return True


def _working_day(day: date, _timing: Timing) -> bool:
    return day.weekday() in _WORKING_DAYS


def _its_weekday(day: date, timing: Timing) -> bool:
    return day.weekday() == timing.weekday


def _its_day_of_month(day: date, timing: Timing) -> bool:
    """The timing's day, or the month's last day when the month is shorter."""
    if timing.day_of_month is None:
        return False
    last = monthrange(day.year, day.month)[1]
    return day.day == min(timing.day_of_month, last)


#: What each preset means (Strategy + Registry).
FREQUENCIES: dict[ScheduleFrequency, Frequency] = {
    ScheduleFrequency.HOURLY: _Hourly(),
    ScheduleFrequency.DAILY: _OnDays(_every_day),
    ScheduleFrequency.WEEKDAYS: _OnDays(_working_day),
    ScheduleFrequency.WEEKLY: _OnDays(_its_weekday, frozenset({"hour", "weekday"})),
    ScheduleFrequency.MONTHLY: _OnDays(_its_day_of_month, frozenset({"hour", "day_of_month"})),
}

#: Why a timing cannot be saved without a field its preset uses.
_MISSING = {
    "weekday": "Choose the day of the week it runs on.",
    "day_of_month": "Choose the day of the month it runs on.",
}


@cache
def _known_zones() -> frozenset[str]:
    return frozenset(available_timezones())


def time_zone_error(name: str) -> str | None:
    """Why ``name`` is not an IANA time zone this server knows, or None when it is."""
    if name in _known_zones():
        return None
    return f"Unknown time zone '{name}'. Use an IANA name such as Europe/Paris."


def _zone(name: str) -> ZoneInfo:
    if error := time_zone_error(name):
        raise ValidationFailed(error)
    return ZoneInfo(name)


def checked(timing: Timing) -> Timing:
    """``timing`` as it is saved: a known zone, the fields its preset needs,
    whole minutes, and the fields the preset does not use cleared."""
    _zone(timing.timezone)
    uses = FREQUENCIES[timing.frequency].uses
    for name, problem in _MISSING.items():
        if name in uses and getattr(timing, name) is None:
            raise ValidationFailed(problem)
    hour = timing.at.hour if "hour" in uses else 0
    return Timing(
        frequency=timing.frequency,
        timezone=timing.timezone,
        at=time(hour, timing.at.minute),
        weekday=timing.weekday if "weekday" in uses else None,
        day_of_month=timing.day_of_month if "day_of_month" in uses else None,
    )


def next_run_after(timing: Timing, after: datetime) -> datetime:
    """The first time ``timing`` comes round strictly after ``after`` (an aware
    datetime), as a UTC instant."""
    moment = after.astimezone(timezone.utc)
    return FREQUENCIES[timing.frequency].next_after(timing, _zone(timing.timezone), moment)
