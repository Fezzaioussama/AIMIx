"""Checking a timing before it is saved: known time zones, the day each frequency needs, and
the fields a frequency does not use."""

from __future__ import annotations

from datetime import time

import pytest

from api.exceptions import ValidationFailed
from api.models import ScheduleFrequency as Freq
from api.services.schedules.timing import Timing, checked, next_run_after, time_zone_error
from tests.schedules.support import PARIS, utc


def test_a_known_time_zone_has_no_error() -> None:
    assert time_zone_error(PARIS) is None
    assert time_zone_error("UTC") is None
    assert time_zone_error("America/Argentina/Buenos_Aires") is None


@pytest.mark.parametrize("name", ["", "Mars/Olympus", "../etc/passwd", "/etc/localtime", "paris"])
def test_anything_else_is_an_unknown_time_zone(name: str) -> None:
    assert "Unknown time zone" in (time_zone_error(name) or "")


def test_an_unknown_time_zone_cannot_be_saved_or_used() -> None:
    timing = Timing(Freq.DAILY, "Mars/Olympus", time(9, 0))

    with pytest.raises(ValidationFailed, match="Unknown time zone 'Mars/Olympus'"):
        checked(timing)
    with pytest.raises(ValidationFailed, match="Unknown time zone"):
        next_run_after(timing, utc(2026, 10, 24))


def test_a_weekly_schedule_needs_its_weekday_and_a_monthly_one_its_day() -> None:
    with pytest.raises(ValidationFailed, match="day of the week"):
        checked(Timing(Freq.WEEKLY, "UTC", time(9, 0)))
    with pytest.raises(ValidationFailed, match="day of the month"):
        checked(Timing(Freq.MONTHLY, "UTC", time(9, 0)))


def test_a_timing_is_saved_without_what_its_frequency_does_not_use() -> None:
    noisy = {"weekday": 3, "day_of_month": 17}

    assert checked(Timing(Freq.HOURLY, "UTC", time(7, 15), **noisy)) == Timing(
        Freq.HOURLY, "UTC", time(0, 15)
    )
    assert checked(Timing(Freq.DAILY, "UTC", time(7, 15), **noisy)) == Timing(
        Freq.DAILY, "UTC", time(7, 15)
    )
    assert checked(Timing(Freq.WEEKLY, "UTC", time(7, 15), **noisy)) == Timing(
        Freq.WEEKLY, "UTC", time(7, 15), weekday=3
    )
    assert checked(Timing(Freq.MONTHLY, "UTC", time(7, 15), **noisy)) == Timing(
        Freq.MONTHLY, "UTC", time(7, 15), day_of_month=17
    )


def test_seconds_are_dropped_and_checking_twice_changes_nothing() -> None:
    once = checked(Timing(Freq.DAILY, PARIS, time(7, 15, 42, 5)))

    assert once.at == time(7, 15)
    assert checked(once) == once
