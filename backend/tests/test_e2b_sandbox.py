"""The E2B adapter against the in-memory SDK stand-ins of e2b_fakes: offline,
short-lived sandboxes, the translation of what the SDK returns, the stream and
download budgets, and error mapping. No network and no key."""

from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any

import httpx
import pytest
from e2b import (
    AuthenticationException,
    FileNotFoundException,
    FileType,
    ServiceBusyException,
    TimeoutException,
)
from e2b_code_interpreter import Execution, ExecutionError, Logs, Result

from api.services.toolbox.e2b_sandbox import OUTPUT_DEPTH, E2BSandboxOpener
from api.services.toolbox.sandbox import (
    CodeError,
    CodeExecution,
    OutputEntry,
    SandboxError,
    SandboxFile,
    SandboxTimedOut,
)
from config.logging_setup import configure_logging
from tests.e2b_fakes import KEY, FakeSdkSandbox, entry, opened


@pytest.mark.asyncio
async def test_sandboxes_are_created_offline_short_lived_and_killed_on_timeout() -> None:
    calls: list[dict[str, Any]] = []

    await opened(FakeSdkSandbox(), calls)

    assert calls == [
        {
            "timeout": 13,
            "allow_internet_access": False,
            "network": {"allow_public_traffic": False},
            "lifecycle": {"on_timeout": "kill"},
            "api_key": KEY,
            "request_timeout": 12.5,
        }
    ]


@pytest.mark.asyncio
async def test_inputs_are_written_below_the_input_directory() -> None:
    sdk = FakeSdkSandbox()

    await (await opened(sdk)).upload(SandboxFile("data/sales.csv", b"a,b\n"))

    assert sdk.files.written == {"/home/user/inputs/data/sales.csv": b"a,b\n"}


@pytest.mark.asyncio
async def test_an_execution_is_translated_from_the_sdk() -> None:
    execution = Execution(
        results=[
            Result(png=base64.b64encode(b"\x89PNG one").decode()),
            Result(text="42", is_main_result=True),
            Result(png="abc"),  # not valid base64: dropped, not fatal
        ],
        logs=Logs(stdout=["a\n", "b\n"], stderr=["warning\n"]),
        error=ExecutionError("ValueError", "bad row", "Traceback ..."),
    )
    sdk = FakeSdkSandbox(execution)

    result = await (await opened(sdk)).execute("print('a')")

    assert result == CodeExecution(
        stdout="a\nb\n",
        stderr="warning\n",
        result="42",
        error=CodeError("ValueError", "bad row", "Traceback ..."),
        charts=(b"\x89PNG one",),
    )
    assert sdk.files.made == ["/home/user/outputs"]
    assert sdk.runs == [("print('a')", {"language": "python", "timeout": 12.5})]


@pytest.mark.asyncio
async def test_a_run_that_streams_too_much_back_is_stopped() -> None:
    sdk = FakeSdkSandbox(Execution(logs=Logs(stdout=["12345\n"] * 1_000)))

    result = await (await opened(sdk, max_stream=10)).execute("while True: print(12345)")

    assert sdk.streamed == 2  # the second line went over the budget: reading stopped
    assert result == CodeExecution(
        stdout="12345\n",
        error=CodeError(
            "OutputLimitExceeded", "The run sent back more than 10 characters and was stopped.", ""
        ),
    )


@pytest.mark.asyncio
async def test_displayed_results_count_against_the_stream_budget() -> None:
    chart = base64.b64encode(b"\x89PNG" * 100).decode()
    sdk = FakeSdkSandbox(Execution(results=[Result(png=chart), Result(json={"rows": "x" * 900})]))

    result = await (await opened(sdk, max_stream=len(chart) + 100)).execute("plot()")

    assert result.charts == (b"\x89PNG" * 100,)
    assert result.error is not None
    assert result.error.name == "OutputLimitExceeded"


@pytest.mark.asyncio
async def test_outputs_are_the_regular_files_below_the_output_directory() -> None:
    sdk = FakeSdkSandbox()
    sdk.files.entries = [
        entry("/home/user/outputs/report.csv", FileType.FILE, 10),
        entry("/home/user/outputs/charts", FileType.DIR),
        entry("/home/user/outputs/charts/a.png", FileType.FILE, 5),
        entry("/home/user/outputs/link", FileType.SYMLINK, 3),
        entry("/home/user/elsewhere.txt", FileType.FILE, 1),
    ]

    outputs = await (await opened(sdk)).list_outputs()

    assert outputs == [OutputEntry("report.csv", 10), OutputEntry("charts/a.png", 5)]
    assert sdk.files.listed == [("/home/user/outputs", OUTPUT_DEPTH)]


@pytest.mark.asyncio
async def test_a_removed_output_directory_means_no_outputs() -> None:
    sdk = FakeSdkSandbox()
    sdk.files.error = FileNotFoundException("/home/user/outputs not found")

    assert await (await opened(sdk)).list_outputs() == []


@pytest.mark.asyncio
async def test_download_and_close() -> None:
    sdk = FakeSdkSandbox()
    sdk.files.contents = {"/home/user/outputs/charts/a.png": b"png bytes"}
    sandbox = await opened(sdk)

    assert await sandbox.download("charts/a.png", 9) == b"png bytes"
    assert sdk.files.streams[0].closed
    await sandbox.close()
    assert sdk.killed


@pytest.mark.asyncio
async def test_a_download_stops_as_soon_as_the_file_outgrows_the_limit() -> None:
    sdk = FakeSdkSandbox()
    sdk.files.contents = {"/home/user/outputs/log.txt": b"x" * 400}

    with pytest.raises(SandboxError, match="grew beyond the 10-byte limit") as raised:
        await (await opened(sdk)).download("log.txt", 10)

    assert type(raised.value) is SandboxError
    assert sdk.files.streams[0].read == 3  # 12 bytes read of 400, then it stopped
    assert sdk.files.streams[0].closed


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure", "expected", "message"),
    [
        (TimeoutException("Execution timed out"), SandboxTimedOut, "timed out"),
        (httpx.ReadTimeout("slow"), SandboxTimedOut, "timed out"),
        (AuthenticationException(f"Bad key {KEY}"), SandboxError, "AuthenticationException"),
        (ServiceBusyException("no capacity"), SandboxError, "ServiceBusyException"),
        (httpx.ConnectError("down"), SandboxError, "ConnectError"),
    ],
)
async def test_sdk_failures_become_sandbox_errors_without_details(
    failure: Exception, expected: type[SandboxError], message: str
) -> None:
    sdk = FakeSdkSandbox()
    sdk.error = failure

    with pytest.raises(expected, match=message) as raised:
        await (await opened(sdk)).execute("go()")

    assert type(raised.value) is expected
    assert raised.value.__cause__ is failure
    assert KEY not in str(raised.value)


@pytest.mark.asyncio
async def test_a_failed_creation_is_a_sandbox_error() -> None:
    async def create(**options: Any) -> FakeSdkSandbox:
        raise AuthenticationException("Invalid API key")

    with pytest.raises(SandboxError, match="AuthenticationException"):
        await E2BSandboxOpener(KEY, 5, 1_000, create)()


@pytest.mark.asyncio
async def test_cancellation_is_not_mistaken_for_a_sandbox_failure() -> None:
    sdk = FakeSdkSandbox()
    sdk.error = asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await (await opened(sdk)).execute("go()")


def test_the_sdk_never_logs_submitted_code_even_at_debug_level() -> None:
    sdk_logger = logging.getLogger("e2b_code_interpreter.code_interpreter_async")
    try:
        configure_logging("DEBUG")
        assert not sdk_logger.isEnabledFor(logging.DEBUG)
        assert logging.getLogger("api").isEnabledFor(logging.DEBUG)
        configure_logging("ERROR")  # and it is never louder than the app
        assert not sdk_logger.isEnabledFor(logging.WARNING)
    finally:
        configure_logging("WARNING")
