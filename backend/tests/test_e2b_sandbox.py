"""The E2B adapter against an in-memory stand-in for the SDK sandbox: no network
and no key. Results are built from the SDK's own data classes, so a change in
their shape fails here rather than in production."""

from __future__ import annotations

import asyncio
import base64
import logging
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any

import httpx
import pytest
from e2b import (
    AuthenticationException,
    EntryInfo,
    FileNotFoundException,
    FileType,
    ServiceBusyException,
    TimeoutException,
)
from e2b_code_interpreter import Execution, ExecutionError, Logs, OutputMessage, Result

from api.services.toolbox.e2b_sandbox import OUTPUT_DEPTH, E2BSandbox, E2BSandboxOpener
from api.services.toolbox.sandbox import (
    CodeError,
    CodeExecution,
    OutputEntry,
    SandboxError,
    SandboxFile,
    SandboxTimedOut,
)
from config.logging_setup import configure_logging

KEY = "e2b-test-key"


def entry(path: str, kind: FileType, size: int = 0) -> EntryInfo:
    return EntryInfo(
        name=PurePosixPath(path).name,
        type=kind,
        path=path,
        size=size,
        mode=0o644,
        permissions="rw-r--r--",
        owner="user",
        group="user",
        modified_time=datetime(2026, 10, 24, tzinfo=timezone.utc),
    )


class FakeStream:
    """The SDK's streamed download: an async context manager over chunks."""

    def __init__(self, data: bytes) -> None:
        self._chunks = [data[start : start + 4] for start in range(0, len(data), 4)]
        self.read = 0
        self.closed = False

    async def __aenter__(self) -> FakeStream:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        self.closed = True

    def __aiter__(self) -> FakeStream:
        return self

    async def __anext__(self) -> bytes:
        if not self._chunks:
            raise StopAsyncIteration
        self.read += 1
        return self._chunks.pop(0)


class FakeFiles:
    def __init__(self) -> None:
        self.written: dict[str, bytes] = {}
        self.made: list[str] = []
        self.entries: list[EntryInfo] = []
        self.listed: list[tuple[str, int]] = []
        self.contents: dict[str, bytes] = {}
        self.streams: list[FakeStream] = []
        self.error: Exception | None = None

    async def write(self, path: str, data: bytes) -> None:
        self.written[path] = data

    async def make_dir(self, path: str) -> bool:
        self.made.append(path)
        return True

    async def list(self, path: str, depth: int = 1) -> list[EntryInfo]:
        if self.error:
            raise self.error
        self.listed.append((path, depth))
        return self.entries

    async def read(self, path: str, format: str = "text") -> FakeStream:
        assert format == "stream"
        self.streams.append(FakeStream(self.contents[path]))
        return self.streams[-1]


class FakeSdkSandbox:
    def __init__(self, execution: Execution | None = None) -> None:
        self.files = FakeFiles()
        self.execution = execution or Execution()
        self.error: BaseException | None = None
        self.runs: list[tuple[str, dict[str, Any]]] = []
        self.streamed = 0
        self.killed = False

    async def run_code(self, code: str, **options: Any) -> Execution:
        """Streams ``execution`` through the callbacks, as the SDK does."""
        self.runs.append((code, {k: v for k, v in options.items() if not k.startswith("on_")}))
        if self.error:
            raise self.error
        messages: list[tuple[str, Any]] = [
            *(("on_stdout", OutputMessage(line, 0)) for line in self.execution.logs.stdout),
            *(("on_stderr", OutputMessage(line, 0, True)) for line in self.execution.logs.stderr),
            *(("on_result", result) for result in self.execution.results),
        ]
        if self.execution.error:
            messages.append(("on_error", self.execution.error))
        for callback, message in messages:
            self.streamed += 1
            options[callback](message)
        return self.execution

    async def kill(self) -> bool:
        self.killed = True
        return True


async def opened(
    sdk: FakeSdkSandbox, calls: list[dict[str, Any]] | None = None, max_stream: int = 1_000
) -> E2BSandbox:
    """Open the adapter over ``sdk``, recording the creation options in ``calls``."""
    recorded = [] if calls is None else calls

    async def create(**options: Any) -> FakeSdkSandbox:
        recorded.append(options)
        return sdk

    return await E2BSandboxOpener(KEY, 12.5, max_stream, create)()


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
async def test_displayed_charts_count_against_the_stream_budget() -> None:
    chart = base64.b64encode(b"\x89PNG" * 100).decode()
    sdk = FakeSdkSandbox(Execution(results=[Result(png=chart), Result(png=chart)]))

    result = await (await opened(sdk, max_stream=len(chart) + 1)).execute("plot()")

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
