"""The retry policy (llm/retry.py): what is retried, how often, and how long
each retry waits. Every wait is recorded by a fake clock, never slept."""

from __future__ import annotations

import email.utils
import logging
from collections.abc import AsyncIterator, Callable, Iterator

import httpx
import openai
import pytest
from openrouter.errors import NoResponseError

from llm.retry import Retrier, RetryPolicy
from tests.retry_fakes import (
    NOW,
    FakeClock,
    openai_connection_error,
    openai_status,
    openai_timeout,
    openrouter_status,
)

TRANSIENT_STATUSES = [408, 429, 500, 502, 503, 504]
PERMANENT_STATUSES = [400, 401, 402, 403, 404, 409, 413, 422, 501, 524, 529]
STATUS_ERRORS = [openai_status, openrouter_status]
Script = tuple[list[str], BaseException | None]


class Flaky:
    """A call that raises the given errors, one per attempt, then answers."""

    def __init__(self, *errors: BaseException) -> None:
        self.errors = list(errors)
        self.calls = 0

    def __call__(self) -> str:
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        return "ok"

    async def acall(self) -> str:
        return self()


class FlakyStream:
    """Each opening yields its script's items, then raises its error if any."""

    def __init__(self, *scripts: Script) -> None:
        self.scripts = list(scripts)
        self.opened = 0

    def _next_script(self) -> Script:
        self.opened += 1
        return self.scripts.pop(0)

    def open(self) -> Iterator[str]:
        items, error = self._next_script()
        yield from items
        if error is not None:
            raise error

    async def aopen(self) -> AsyncIterator[str]:
        items, error = self._next_script()
        for item in items:
            yield item
        if error is not None:
            raise error


def retrier(clock: FakeClock, max_retries: int = 2, maximum: float = 20.0) -> Retrier:
    policy = RetryPolicy(max_retries=max_retries, base_delay_seconds=1.0, max_delay_seconds=maximum)
    return Retrier(policy, "test-provider", "vendor/model", clock.retry_clock())


@pytest.mark.parametrize("build", STATUS_ERRORS)
@pytest.mark.parametrize("status", TRANSIENT_STATUSES)
def test_a_transient_status_is_retried(build: Callable[[int], Exception], status: int) -> None:
    clock = FakeClock()
    call = Flaky(build(status))
    assert retrier(clock).call(call) == "ok"
    assert (call.calls, len(clock.waits)) == (2, 1)


@pytest.mark.parametrize("build", STATUS_ERRORS)
@pytest.mark.parametrize("status", PERMANENT_STATUSES)
def test_any_other_status_fails_at_once(build: Callable[[int], Exception], status: int) -> None:
    clock = FakeClock()
    error = build(status)
    call = Flaky(error)
    with pytest.raises(type(error)) as raised:
        retrier(clock).call(call)
    assert raised.value is error
    assert (call.calls, clock.waits) == (1, [])


@pytest.mark.parametrize(
    "error",
    [
        openai_connection_error(),
        httpx.ConnectError("connection refused"),
        httpx.ReadError("connection reset"),
        httpx.RemoteProtocolError("server disconnected without a response"),
        NoResponseError(),
    ],
    ids=lambda error: type(error).__name__,
)
def test_a_failed_connection_is_retried(error: Exception) -> None:
    call = Flaky(error)
    assert retrier(FakeClock()).call(call) == "ok"
    assert call.calls == 2


@pytest.mark.parametrize(
    "error",
    [
        openai_timeout(),
        httpx.ReadTimeout("too slow"),
        httpx.ConnectTimeout("too slow"),
        TimeoutError(),
        ValueError("a bug, not a provider failure"),
    ],
    ids=lambda error: type(error).__name__,
)
def test_timeouts_and_unrelated_errors_are_not_retried(error: Exception) -> None:
    call = Flaky(error)
    with pytest.raises(type(error)):
        retrier(FakeClock()).call(call)
    assert call.calls == 1


def test_retries_stop_at_the_limit_and_the_last_error_surfaces() -> None:
    clock = FakeClock()
    errors = [openai_status(503) for _ in range(3)]
    call = Flaky(*errors)
    with pytest.raises(openai.APIStatusError) as raised:
        retrier(clock, max_retries=2).call(call)
    assert raised.value is errors[-1]
    assert (call.calls, len(clock.waits)) == (3, 2)


def test_zero_retries_is_a_single_attempt() -> None:
    call = Flaky(openai_status(503))
    with pytest.raises(openai.APIStatusError):
        retrier(FakeClock(), max_retries=0).call(call)
    assert call.calls == 1


def test_backoff_doubles_with_full_jitter_up_to_the_maximum_delay() -> None:
    clock = FakeClock()
    retrier(clock, max_retries=5, maximum=5.0).call(Flaky(*[openai_status(502)] * 5))
    assert clock.bounds == [(0.0, 1.0), (0.0, 2.0), (0.0, 4.0), (0.0, 5.0), (0.0, 5.0)]
    assert clock.waits == [1.0, 2.0, 4.0, 5.0, 5.0]


@pytest.mark.parametrize("build", STATUS_ERRORS)
@pytest.mark.parametrize(
    ("header", "wait"),
    [
        ("3", 3.0),
        ("1.5", 1.5),
        (email.utils.formatdate(NOW + 7, usegmt=True), 7.0),
        ("120", 20.0),
        (email.utils.formatdate(NOW - 60, usegmt=True), 0.0),
    ],
    ids=["seconds", "fractional", "http-date", "capped", "past-date"],
)
def test_retry_after_is_honoured_up_to_the_maximum_delay(
    build: Callable[[int, dict[str, str]], Exception], header: str, wait: float
) -> None:
    clock = FakeClock()
    retrier(clock).call(Flaky(build(429, {"Retry-After": header})))
    assert clock.waits == [wait]
    assert clock.bounds == []  # the provider chose the wait: no jitter


@pytest.mark.parametrize("header", ["soon", "nan", "Wed, 21 Oct 99999 07:28:00 GMT"])
def test_an_unreadable_retry_after_falls_back_to_backoff(header: str) -> None:
    clock = FakeClock()
    retrier(clock).call(Flaky(openai_status(503, {"Retry-After": header})))
    assert clock.bounds == [(0.0, 1.0)]


def test_each_retry_is_logged_with_its_reason_and_wait(caplog: pytest.LogCaptureFixture) -> None:
    errors = (openai_status(429, {"Retry-After": "2"}), openai_connection_error())
    with caplog.at_level(logging.WARNING, logger="llm.retry"):
        retrier(FakeClock()).call(Flaky(*errors))
    prefix = "llm.retry provider=test-provider model=vendor/model"
    assert [record.getMessage() for record in caplog.records] == [
        f"{prefix} attempt=1/3 reason=http_429 delay_s=2.00",
        f"{prefix} attempt=2/3 reason=APIConnectionError delay_s=2.00",
    ]
    assert {record.levelno for record in caplog.records} == {logging.WARNING}


@pytest.mark.asyncio
async def test_async_calls_follow_the_same_policy() -> None:
    clock = FakeClock()
    call = Flaky(openrouter_status(503), httpx.ConnectError("refused"), openrouter_status(400))
    with pytest.raises(type(call.errors[-1])):
        await retrier(clock, max_retries=5).acall(call.acall)
    assert (call.calls, clock.waits) == (3, [1.0, 2.0])


def test_a_stream_is_retried_until_its_first_item() -> None:
    stream = FlakyStream(([], openai_connection_error()), (["a", "b"], None))
    assert list(retrier(FakeClock()).stream(stream.open)) == ["a", "b"]
    assert stream.opened == 2


def test_a_stream_that_produced_output_is_never_replayed() -> None:
    stream = FlakyStream((["a"], openai_connection_error()), (["a", "b"], None))
    received: list[str] = []
    with pytest.raises(openai.APIConnectionError):
        received.extend(retrier(FakeClock()).stream(stream.open))
    assert (received, stream.opened) == (["a"], 1)


def test_an_empty_stream_is_not_a_failure() -> None:
    stream = FlakyStream(([], None))
    assert list(retrier(FakeClock()).stream(stream.open)) == []
    assert stream.opened == 1


@pytest.mark.asyncio
async def test_an_async_stream_is_retried_only_before_its_first_item() -> None:
    clock = FakeClock()
    retried = FlakyStream(([], openrouter_status(502)), (["a", "b"], None))
    assert [item async for item in retrier(clock).astream(retried.aopen)] == ["a", "b"]
    assert retried.opened == 2

    started = FlakyStream((["a"], openrouter_status(502)), (["a", "b"], None))
    received: list[str] = []
    with pytest.raises(type(openrouter_status(502))):
        async for item in retrier(clock).astream(started.aopen):
            received.append(item)
    assert (received, started.opened) == (["a"], 1)
