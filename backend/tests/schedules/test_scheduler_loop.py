"""The scheduler's thread and its place in the app: it ticks until stopped, survives a failing
tick, is built from settings, and the lifespan starts it and stops it before the executor."""

from __future__ import annotations

import threading

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.services.schedules.scheduler import IdleScheduler, SchedulerLoop, build_scheduler
from tests.conftest import TEST_SETTINGS
from tests.schedules.support import WAIT_SECONDS


def test_the_loop_ticks_until_it_is_stopped() -> None:
    enough = threading.Event()
    calls: list[int] = []

    def tick() -> None:
        calls.append(1)
        if len(calls) == 3:
            enough.set()

    loop = SchedulerLoop(tick, interval=0.001, grace=WAIT_SECONDS)
    loop.start()
    loop.start()  # a second start changes nothing
    assert enough.wait(WAIT_SECONDS)
    loop.stop()
    count = len(calls)
    loop.stop()  # and neither does a second stop

    assert len(calls) == count  # nothing ticks once stop has returned


def test_a_failing_tick_does_not_end_the_loop() -> None:
    survived = threading.Event()
    calls: list[int] = []

    def tick() -> None:
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("the database is briefly unavailable")
        survived.set()

    loop = SchedulerLoop(tick, interval=0.001, grace=WAIT_SECONDS)
    loop.start()
    try:
        assert survived.wait(WAIT_SECONDS)
    finally:
        loop.stop()


def test_a_stopped_loop_can_start_again() -> None:
    ticked = threading.Event()
    loop = SchedulerLoop(ticked.set, interval=0.001, grace=WAIT_SECONDS)

    loop.start()
    assert ticked.wait(WAIT_SECONDS)
    loop.stop()
    ticked.clear()
    loop.start()
    try:
        assert ticked.wait(WAIT_SECONDS)
    finally:
        loop.stop()


def test_restarting_while_a_slow_tick_is_still_running_leaves_one_loop() -> None:
    first_tick_running, release = threading.Event(), threading.Event()
    enough = threading.Event()
    ticking: list[int] = []

    def tick() -> None:
        ticking.append(threading.get_ident())
        if len(ticking) == 1:
            first_tick_running.set()
            release.wait(WAIT_SECONDS)  # a tick that outlives stop()'s grace
        elif len(ticking) >= 6:
            enough.set()

    loop = SchedulerLoop(tick, interval=0.001, grace=0.01)
    loop.start()
    assert first_tick_running.wait(WAIT_SECONDS)
    loop.stop()  # gives up waiting for the slow tick after its grace
    loop.start()  # a new thread, which must not revive the old one
    release.set()
    try:
        assert enough.wait(WAIT_SECONDS)
    finally:
        loop.stop()

    # After the first (slow) tick, every tick came from the same, new thread.
    assert len(set(ticking[1:])) == 1
    assert ticking[1] != ticking[0]


def test_the_scheduler_is_built_from_settings(app: FastAPI) -> None:
    database, executor = app.state.database, app.state.run_executor
    enabled = TEST_SETTINGS.model_copy(update={"scheduler_enabled": True})

    idle = build_scheduler(database, executor, TEST_SETTINGS)
    idle.start()
    idle.stop()

    assert isinstance(idle, IdleScheduler)
    assert isinstance(build_scheduler(database, executor, enabled), SchedulerLoop)


class Recorder:
    """Stands in for the scheduler and the executor, noting when each starts or stops."""

    def __init__(self, events: list[str]) -> None:
        self.events = events

    def start(self) -> None:
        self.events.append("scheduler started")

    def stop(self) -> None:
        self.events.append("scheduler stopped")

    def shutdown(self) -> None:
        self.events.append("executor stopped")


def test_the_app_starts_the_scheduler_and_stops_it_before_the_executor(app: FastAPI) -> None:
    events: list[str] = []
    recorder = Recorder(events)
    app.state.scheduler = recorder
    app.state.run_executor = recorder

    with TestClient(app):
        assert events == ["scheduler started"]

    assert events == ["scheduler started", "scheduler stopped", "executor stopped"]
