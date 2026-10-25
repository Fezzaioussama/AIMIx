"""When a schedule runs next: presets read on a time zone's clock, across
daylight-saving changes, month ends and weekends (pure, no clock, no database)."""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from itertools import pairwise
from zoneinfo import ZoneInfo

import pytest

from api.exceptions import ValidationFailed
from api.models import ScheduleFrequency as Freq
from api.services.schedules.timing import (
    FREQUENCIES,
    Timing,
    checked,
    next_run_after,
    time_zone_error,
)

PARIS = "Europe/Paris"


def utc(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def chain(timing: Timing, start: datetime, count: int) -> list[datetime]:
    """The next ``count`` times, each found after the one before."""
    found: list[datetime] = []
    at = start
    for _ in range(count):
        at = next_run_after(timing, at)
        found.append(at)
    return found


def local(moment: datetime, zone: str) -> str:
    """A UTC instant as that zone's wall clock, with its offset: 2026-03-29 03:30+02:00."""
    return moment.astimezone(ZoneInfo(zone)).strftime("%Y-%m-%d %H:%M%z")


# --- every preset: strictly after, in UTC ----------------------------------------


def test_every_frequency_has_a_rule() -> None:
    assert set(FREQUENCIES) == set(Freq)


def test_the_next_time_is_strictly_after_and_in_utc() -> None:
    timing = Timing(Freq.DAILY, "UTC", time(9, 0))

    assert next_run_after(timing, utc(2026, 10, 24, 8, 59)) == utc(2026, 10, 24, 9, 0)
    assert next_run_after(timing, utc(2026, 10, 24, 9, 0)) == utc(2026, 10, 25, 9, 0)
    paris = datetime(2026, 10, 24, 10, 0, tzinfo=ZoneInfo(PARIS))  # 08:00 UTC
    assert next_run_after(timing, paris) == utc(2026, 10, 24, 9, 0)
    assert next_run_after(timing, paris).tzinfo == timezone.utc


def test_a_fraction_of_a_second_past_a_time_is_past_it() -> None:
    timing = Timing(Freq.DAILY, "UTC", time(9, 0))

    after = datetime(2026, 10, 24, 9, 0, 0, 1, tzinfo=timezone.utc)

    assert next_run_after(timing, after) == utc(2026, 10, 25, 9, 0)


# --- hourly -----------------------------------------------------------------------


def test_hourly_runs_at_its_minute_every_hour() -> None:
    timing = Timing(Freq.HOURLY, "UTC", time(0, 15))

    assert next_run_after(timing, utc(2026, 10, 24, 10, 0)) == utc(2026, 10, 24, 10, 15)
    assert next_run_after(timing, utc(2026, 10, 24, 10, 15)) == utc(2026, 10, 24, 11, 15)
    assert next_run_after(timing, utc(2026, 10, 24, 23, 45)) == utc(2026, 10, 25, 0, 15)


def test_hourly_uses_the_minutes_of_its_time_only() -> None:
    timing = Timing(Freq.HOURLY, "UTC", time(7, 30))

    assert next_run_after(timing, utc(2026, 10, 24, 3, 0)) == utc(2026, 10, 24, 3, 30)


def test_hourly_follows_a_zone_that_is_half_an_hour_off_utc() -> None:
    timing = Timing(Freq.HOURLY, "Asia/Kolkata", time(0, 0))  # UTC+5:30

    assert next_run_after(timing, utc(2026, 10, 24, 10, 0)) == utc(2026, 10, 24, 10, 30)


def test_hourly_runs_every_real_hour_when_the_clocks_go_back() -> None:
    timing = Timing(Freq.HOURLY, PARIS, time(0, 30))

    times = chain(timing, utc(2026, 10, 24, 23, 0), 5)  # the night of 25 Oct 2026

    assert times == [utc(2026, 10, 24, 23, 30)] + [utc(2026, 10, 25, h, 30) for h in (0, 1, 2, 3)]
    # 02:30 on the Paris clock happens twice, and both are run.
    assert [local(moment, PARIS) for moment in times[1:3]] == [
        "2026-10-25 02:30+0200",
        "2026-10-25 02:30+0100",
    ]


def test_hourly_does_not_run_in_the_hour_the_clocks_skip() -> None:
    timing = Timing(Freq.HOURLY, PARIS, time(0, 30))

    times = chain(timing, utc(2026, 3, 28, 23, 0), 4)  # the night of 29 Mar 2026

    assert [local(moment, PARIS) for moment in times] == [
        "2026-03-29 00:30+0100",
        "2026-03-29 01:30+0100",
        "2026-03-29 03:30+0200",
        "2026-03-29 04:30+0200",
    ]


# --- daily and weekdays -----------------------------------------------------------


def test_daily_runs_today_while_its_time_is_ahead_and_tomorrow_after() -> None:
    timing = Timing(Freq.DAILY, "UTC", time(9, 0))

    assert next_run_after(timing, utc(2026, 10, 24, 6, 0)) == utc(2026, 10, 24, 9, 0)
    assert next_run_after(timing, utc(2026, 10, 24, 12, 0)) == utc(2026, 10, 25, 9, 0)


def test_daily_keeps_its_local_time_whatever_the_utc_offset() -> None:
    timing = Timing(Freq.DAILY, PARIS, time(9, 0))

    assert next_run_after(timing, utc(2026, 1, 15)) == utc(2026, 1, 15, 8, 0)  # UTC+1
    assert next_run_after(timing, utc(2026, 7, 15)) == utc(2026, 7, 15, 7, 0)  # UTC+2


def test_daily_counts_days_on_the_zones_calendar_not_utcs() -> None:
    timing = Timing(Freq.DAILY, "Asia/Tokyo", time(9, 0))  # UTC+9

    # 23:30 UTC on the 24th is already 08:30 on the 25th in Tokyo.
    assert next_run_after(timing, utc(2026, 10, 24, 23, 30)) == utc(2026, 10, 25, 0, 0)


def test_daily_time_in_the_hour_the_clocks_skip_runs_as_much_later_as_they_jumped() -> None:
    paris = Timing(Freq.DAILY, PARIS, time(2, 30))
    new_york = Timing(Freq.DAILY, "America/New_York", time(2, 30))

    paris_times = chain(paris, utc(2026, 3, 28, 12), 3)
    new_york_times = chain(new_york, utc(2026, 3, 7, 12), 3)

    # 02:30 does not exist on 29 Mar in Paris; it becomes 03:30, then 02:30 resumes.
    assert [local(moment, PARIS) for moment in paris_times] == [
        "2026-03-29 03:30+0200",
        "2026-03-30 02:30+0200",
        "2026-03-31 02:30+0200",
    ]
    assert [local(moment, "America/New_York") for moment in new_york_times] == [
        "2026-03-08 03:30-0400",
        "2026-03-09 02:30-0400",
        "2026-03-10 02:30-0400",
    ]


def test_daily_time_that_happens_twice_runs_once_the_first_time() -> None:
    timing = Timing(Freq.DAILY, PARIS, time(2, 30))

    times = chain(timing, utc(2026, 10, 24, 12), 3)

    assert [local(moment, PARIS) for moment in times] == [
        "2026-10-25 02:30+0200",  # the first 02:30, not the second one an hour later
        "2026-10-26 02:30+0100",
        "2026-10-27 02:30+0100",
    ]


def test_weekdays_skip_the_weekend() -> None:
    timing = Timing(Freq.WEEKDAYS, PARIS, time(9, 0))

    times = chain(timing, utc(2026, 10, 23, 12), 4)  # Friday 23 Oct, after 09:00

    assert [local(moment, PARIS)[:16] for moment in times] == [
        "2026-10-26 09:00",  # Monday
        "2026-10-27 09:00",
        "2026-10-28 09:00",
        "2026-10-29 09:00",
    ]


def test_weekdays_include_friday_when_its_time_has_not_come() -> None:
    timing = Timing(Freq.WEEKDAYS, "UTC", time(9, 0))

    assert next_run_after(timing, utc(2026, 10, 23, 6)) == utc(2026, 10, 23, 9)  # Friday
    assert next_run_after(timing, utc(2026, 10, 24, 6)) == utc(2026, 10, 26, 9)  # Saturday


# --- weekly -----------------------------------------------------------------------


def test_weekly_runs_on_its_weekday() -> None:
    monday = Timing(Freq.WEEKLY, "UTC", time(9, 0), weekday=0)

    assert next_run_after(monday, utc(2026, 10, 20, 12)) == utc(2026, 10, 26, 9)  # from Tuesday
    assert next_run_after(monday, utc(2026, 10, 26, 8)) == utc(2026, 10, 26, 9)  # same day, ahead
    assert next_run_after(monday, utc(2026, 10, 26, 9)) == utc(2026, 11, 2, 9)  # a week later


def test_weekly_on_sunday() -> None:
    sunday = Timing(Freq.WEEKLY, "UTC", time(18, 0), weekday=6)

    assert next_run_after(sunday, utc(2026, 10, 24, 12)) == utc(2026, 10, 25, 18)


def test_weekly_weekday_is_the_zones_not_utcs() -> None:
    monday = Timing(Freq.WEEKLY, "Pacific/Auckland", time(9, 0), weekday=0)  # UTC+13 in October

    # Monday 09:00 in Auckland is still Sunday evening in UTC.
    assert next_run_after(monday, utc(2026, 10, 24, 12)) == utc(2026, 10, 25, 20)


# --- monthly ----------------------------------------------------------------------


def test_monthly_runs_on_its_day_of_the_month() -> None:
    timing = Timing(Freq.MONTHLY, "UTC", time(9, 0), day_of_month=15)

    assert next_run_after(timing, utc(2026, 10, 10)) == utc(2026, 10, 15, 9)
    assert next_run_after(timing, utc(2026, 10, 24)) == utc(2026, 11, 15, 9)
    assert next_run_after(timing, utc(2026, 12, 20)) == utc(2027, 1, 15, 9)


def test_monthly_day_past_the_end_of_a_month_is_its_last_day() -> None:
    thirty_first = Timing(Freq.MONTHLY, "UTC", time(9, 0), day_of_month=31)

    times = chain(thirty_first, utc(2026, 1, 1), 5)

    assert [moment.date().isoformat() for moment in times] == [
        "2026-01-31",
        "2026-02-28",
        "2026-03-31",
        "2026-04-30",
        "2026-05-31",
    ]


def test_monthly_day_in_february_follows_leap_years() -> None:
    thirtieth = Timing(Freq.MONTHLY, "UTC", time(9, 0), day_of_month=30)
    twenty_ninth = Timing(Freq.MONTHLY, "UTC", time(9, 0), day_of_month=29)

    assert next_run_after(thirtieth, utc(2028, 2, 1)).date().isoformat() == "2028-02-29"
    assert next_run_after(twenty_ninth, utc(2027, 2, 1)).date().isoformat() == "2027-02-28"
    assert next_run_after(twenty_ninth, utc(2027, 2, 28, 10)).date().isoformat() == "2027-03-29"


def test_monthly_waits_a_whole_month_after_a_short_one() -> None:
    thirty_first = Timing(Freq.MONTHLY, "UTC", time(9, 0), day_of_month=31)

    # The 30th of April was the last day of April: the run came on it.
    assert next_run_after(thirty_first, utc(2026, 4, 30, 9)) == utc(2026, 5, 31, 9)


# --- the same rules, over a whole year and several zones ---------------------------

#: (frequency, shortest and longest gap between two consecutive times, in hours).
GAPS = [
    (Freq.HOURLY, 1, 1),
    (Freq.DAILY, 23, 25),
    (Freq.WEEKDAYS, 23, 73),
    (Freq.WEEKLY, 167, 169),
    (Freq.MONTHLY, 28 * 24 - 1, 31 * 24 + 1),
]
ZONES = [PARIS, "America/New_York", "Australia/Sydney", "Asia/Kolkata", "UTC"]
#: Two windows that hold this year's clock changes (New York 8 Mar and 1 Nov,
#: Paris 29 Mar and 25 Oct, Sydney 4 Oct), and how many times to look at in each.
STARTS = [utc(2026, 3, 1), utc(2026, 10, 1)]
COUNTS = {Freq.HOURLY: 800, Freq.DAILY: 60, Freq.WEEKDAYS: 45, Freq.WEEKLY: 20, Freq.MONTHLY: 14}


@pytest.mark.parametrize("start", STARTS)
@pytest.mark.parametrize("zone", ZONES)
@pytest.mark.parametrize(("frequency", "shortest", "longest"), GAPS)
def test_times_keep_coming_at_a_steady_pace_across_clock_changes(
    frequency: Freq, shortest: int, longest: int, zone: str, start: datetime
) -> None:
    # 02:30 is inside a skipped or repeated hour somewhere on this list.
    timing = Timing(frequency, zone, time(2, 30), weekday=2, day_of_month=29)

    times = chain(timing, start, COUNTS[frequency])

    gaps = [(later - earlier) / timedelta(hours=1) for earlier, later in pairwise(times)]
    assert all(shortest <= gap <= longest for gap in gaps), (frequency, zone, gaps)


# --- checking a timing before it is saved ------------------------------------------


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
