"""E2B adapter for the ``CodeSandbox`` port, over the e2b-code-interpreter SDK's
async API (AGENTS.md §7 Adapter / Gateway). The only module that imports it.

Each sandbox is created with no internet access and with authenticated URLs, so
code cannot send workspace data anywhere; what it prints and the files it saves
come back only to the agent. Its lifetime is SANDBOX_TIMEOUT_SECONDS and a
timeout kills it (never pauses it), so a sandbox the app fails to close is
still destroyed. Every request to E2B is bounded by the same timeout. Retries
are the SDK's own: bounded, with backoff, and never a sandbox creation that may
already have succeeded.

The SDK keeps everything a run streams back in memory, so a run that streams
more than SANDBOX_MAX_STREAM_CHARS is stopped: a runaway print loop cannot fill
the server's memory.
"""

from __future__ import annotations

import base64
import binascii
import math
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from pathlib import PurePosixPath
from typing import Any

import httpx
from e2b import FileNotFoundException, FileType, TimeoutException
from e2b_code_interpreter import AsyncSandbox  # type: ignore[import-untyped]

from api.services.toolbox.sandbox import (
    INPUT_DIR,
    OUTPUT_DIR,
    CodeError,
    CodeExecution,
    OutputEntry,
    SandboxError,
    SandboxFile,
    SandboxTimedOut,
)

#: How many directory levels below OUTPUT_DIR are collected.
OUTPUT_DEPTH = 5
#: The payloads of a displayed result that count against the stream budget.
RESULT_FORMATS = ("text", "html", "markdown", "svg", "png", "jpeg", "pdf", "latex", "javascript")
_TIMEOUTS = (TimeoutException, TimeoutError, httpx.TimeoutException)

CreateSandbox = Callable[..., Awaitable[Any]]


class _StreamLimitReached(Exception):
    """Raised from an SDK callback to stop reading a run's output."""


@contextmanager
def _sdk_errors() -> Iterator[None]:
    """Re-raise whatever the SDK throws as our own error (the §8 adapter case)."""
    try:
        yield
    except _TIMEOUTS as cause:
        raise SandboxTimedOut("The code sandbox timed out.") from cause
    except Exception as cause:  # the SDK's errors share no base class
        raise SandboxError(f"The code sandbox failed: {type(cause).__name__}.") from cause


def _charts(results: list[Any]) -> Iterator[bytes]:
    for result in results:
        if result.png:
            try:
                yield base64.b64decode(result.png)
            except binascii.Error:
                continue


class _Recorder:
    """Collects one run's output through the SDK callbacks, within a budget."""

    def __init__(self, max_chars: int) -> None:
        self._left = max_chars
        self._limit = max_chars
        self._stdout: list[str] = []
        self._stderr: list[str] = []
        self._results: list[Any] = []
        self._error: CodeError | None = None

    def _spend(self, chars: int) -> None:
        self._left -= chars
        if self._left < 0:
            raise _StreamLimitReached

    def stdout(self, message: Any) -> None:
        self._spend(len(message.line))
        self._stdout.append(message.line)

    def stderr(self, message: Any) -> None:
        self._spend(len(message.line))
        self._stderr.append(message.line)

    def result(self, result: Any) -> None:
        self._spend(sum(len(getattr(result, name) or "") for name in RESULT_FORMATS))
        self._results.append(result)

    def error(self, error: Any) -> None:
        self._error = CodeError(error.name, error.value, error.traceback)

    def stopped(self) -> None:
        message = f"The run sent back more than {self._limit} characters and was stopped."
        self._error = CodeError("OutputLimitExceeded", message, "")

    def execution(self) -> CodeExecution:
        main = next((item.text for item in self._results if item.is_main_result), None)
        return CodeExecution(
            stdout="".join(self._stdout),
            stderr="".join(self._stderr),
            result=main or "",
            error=self._error,
            charts=tuple(_charts(self._results)),
        )


def _outputs(entries: list[Any]) -> list[OutputEntry]:
    root = PurePosixPath(OUTPUT_DIR)
    paths = ((PurePosixPath(entry.path), entry) for entry in entries if entry.type == FileType.FILE)
    return [
        OutputEntry(path.relative_to(root).as_posix(), entry.size)
        for path, entry in paths
        if path.is_relative_to(root)
    ]


class E2BSandbox:
    """One E2B sandbox behind the ``CodeSandbox`` port."""

    def __init__(self, sandbox: Any, timeout_seconds: float, max_stream_chars: int) -> None:
        self._sandbox = sandbox
        self._timeout_seconds = timeout_seconds
        self._max_stream_chars = max_stream_chars

    async def upload(self, file: SandboxFile) -> None:
        with _sdk_errors():
            await self._sandbox.files.write(f"{INPUT_DIR}/{file.path}", file.content)

    async def execute(self, code: str) -> CodeExecution:
        recorder = _Recorder(self._max_stream_chars)
        with _sdk_errors():
            await self._sandbox.files.make_dir(OUTPUT_DIR)
            try:
                await self._sandbox.run_code(
                    code,
                    language="python",
                    timeout=self._timeout_seconds,
                    on_stdout=recorder.stdout,
                    on_stderr=recorder.stderr,
                    on_result=recorder.result,
                    on_error=recorder.error,
                )
            except _StreamLimitReached:
                recorder.stopped()  # closing the sandbox then stops the code itself
        return recorder.execution()

    async def list_outputs(self) -> list[OutputEntry]:
        with _sdk_errors():
            try:
                entries = await self._sandbox.files.list(OUTPUT_DIR, depth=OUTPUT_DEPTH)
            except FileNotFoundException:  # the code removed the directory
                return []
        return _outputs(entries)

    async def download(self, path: str) -> bytes:
        with _sdk_errors():
            content = await self._sandbox.files.read(f"{OUTPUT_DIR}/{path}", format="bytes")
        return bytes(content)

    async def close(self) -> None:
        with _sdk_errors():
            await self._sandbox.kill()


class E2BSandboxOpener:
    """Creates a fresh, offline E2B sandbox for every call (Factory)."""

    def __init__(
        self,
        api_key: str,
        timeout_seconds: float,
        max_stream_chars: int,
        create: CreateSandbox = AsyncSandbox.create,
    ) -> None:
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._max_stream_chars = max_stream_chars
        self._create = create

    async def __call__(self) -> E2BSandbox:
        with _sdk_errors():
            sandbox = await self._create(
                timeout=math.ceil(self._timeout_seconds),
                allow_internet_access=False,
                network={"allow_public_traffic": False},
                lifecycle={"on_timeout": "kill"},
                api_key=self._api_key,
                request_timeout=self._timeout_seconds,
            )
        return E2BSandbox(sandbox, self._timeout_seconds, self._max_stream_chars)
