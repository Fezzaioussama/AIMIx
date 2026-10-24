"""Run code in an isolated sandbox: the port, its value objects and the
lifecycle of one call (AGENTS.md §7 Adapter port; the E2B adapter lives in
``e2b_sandbox.py``).

Every call gets a fresh sandbox that is destroyed afterwards — after success,
after an error or a timeout, and when the agent itself is cancelled — so no
state or user data outlives the call. Failures raise ``SandboxError``, a
``ToolException``: the agent receives it as an error result it can react to.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from operator import attrgetter
from time import monotonic
from typing import Protocol

import anyio
from langchain_core.tools import ToolException

logger = logging.getLogger(__name__)

#: Where uploaded input files appear, and the directory collected after the run.
INPUT_DIR = "/home/user/inputs"
OUTPUT_DIR = "/home/user/outputs"


class SandboxError(ToolException):
    """The sandbox could not run the code; the message is safe to show the agent."""


class SandboxTimedOut(SandboxError):
    """The call did not finish within SANDBOX_TIMEOUT_SECONDS."""


@dataclass(frozen=True)
class SandboxFile:
    """A file going into or out of a sandbox; ``path`` is relative and POSIX."""

    path: str
    content: bytes


@dataclass(frozen=True)
class OutputEntry:
    """A file the code left below OUTPUT_DIR, not downloaded yet."""

    path: str
    size: int


@dataclass(frozen=True)
class CodeError:
    """An exception the code raised: its class name, message and traceback."""

    name: str
    value: str
    traceback: str


@dataclass(frozen=True)
class CodeExecution:
    """What the code printed, its final expression's text, and what it raised."""

    stdout: str = ""
    stderr: str = ""
    result: str = ""
    error: CodeError | None = None
    #: PNG images the code displayed (matplotlib charts), in display order.
    charts: tuple[bytes, ...] = ()


@dataclass(frozen=True)
class SandboxLimits:
    timeout_seconds: float
    max_files: int
    max_file_bytes: int
    max_output_chars: int


@dataclass(frozen=True)
class SandboxRun:
    execution: CodeExecution
    #: Charts first (``chart-<n>.png``), then OUTPUT_DIR files, within the limits.
    files: tuple[SandboxFile, ...]
    #: Files left behind for exceeding the file count or size limit.
    skipped: tuple[str, ...]


class CodeSandbox(Protocol):
    """One fresh, isolated sandbox, used for a single call and then closed."""

    async def upload(self, file: SandboxFile) -> None:
        """Make ``file`` readable by the code at INPUT_DIR/<path>."""

    async def execute(self, code: str) -> CodeExecution:
        """Run Python code. An exception it raises is reported, not raised."""

    async def list_outputs(self) -> list[OutputEntry]:
        """The regular files below OUTPUT_DIR, with paths relative to it."""

    async def download(self, path: str) -> bytes:
        """The content of OUTPUT_DIR/<path>."""

    async def close(self) -> None:
        """Destroy the sandbox and everything in it."""


#: Opens a new sandbox for every call (Factory).
SandboxOpener = Callable[[], Awaitable[CodeSandbox]]


@dataclass(frozen=True)
class _Candidate:
    path: str
    size: int
    #: Already in memory (a chart); None means it still has to be downloaded.
    content: bytes | None = None


async def run_in_sandbox(
    open_sandbox: SandboxOpener,
    code: str,
    inputs: Sequence[SandboxFile],
    limits: SandboxLimits,
) -> SandboxRun:
    """Upload ``inputs``, run ``code`` and collect its files in a fresh sandbox.

    Logs ``sandbox.run`` with the outcome and duration, never the code or its
    output (§6).
    """
    started = monotonic()
    try:
        run = await _run(open_sandbox, code, inputs, limits)
    except SandboxError as cause:
        outcome = "timeout" if isinstance(cause, SandboxTimedOut) else "failed"
        logger.warning(
            "sandbox.run outcome=%s error=%s duration_ms=%.1f",
            outcome,
            type(cause.__cause__ or cause).__name__,
            (monotonic() - started) * 1000,
        )
        raise
    logger.info(
        "sandbox.run outcome=%s inputs=%d files=%d duration_ms=%.1f",
        "code_error" if run.execution.error else "ok",
        len(inputs),
        len(run.files),
        (monotonic() - started) * 1000,
    )
    return run


async def _run(
    open_sandbox: SandboxOpener,
    code: str,
    inputs: Sequence[SandboxFile],
    limits: SandboxLimits,
) -> SandboxRun:
    sandbox = await open_sandbox()
    try:
        with anyio.fail_after(limits.timeout_seconds):
            for item in inputs:
                await sandbox.upload(item)
            execution = await sandbox.execute(code)
            files, skipped = await _collect(sandbox, execution.charts, limits)
    except TimeoutError as cause:
        raise SandboxTimedOut(
            f"The code did not finish within {limits.timeout_seconds:g} seconds."
        ) from cause
    finally:
        await _close(sandbox, limits.timeout_seconds)
    return SandboxRun(execution, tuple(files), tuple(skipped))


async def _collect(
    sandbox: CodeSandbox, charts: tuple[bytes, ...], limits: SandboxLimits
) -> tuple[list[SandboxFile], list[str]]:
    """Download only what fits: at most ``max_files`` files of ``max_file_bytes``."""
    candidates = [
        _Candidate(f"chart-{number}.png", len(png), png)
        for number, png in enumerate(charts, start=1)
    ]
    outputs = sorted(await sandbox.list_outputs(), key=attrgetter("path"))
    candidates += [_Candidate(entry.path, entry.size) for entry in outputs]
    fitting = [item for item in candidates if item.size <= limits.max_file_bytes]
    kept = fitting[: limits.max_files]
    files = [
        SandboxFile(
            item.path,
            item.content if item.content is not None else await sandbox.download(item.path),
        )
        for item in kept
    ]
    return files, [item.path for item in candidates if item not in kept]


async def _close(sandbox: CodeSandbox, timeout_seconds: float) -> None:
    """Destroy the sandbox even when the call failed or was cancelled.

    Shielded, so a cancelled agent still closes it, and bounded. A sandbox that
    cannot be closed is logged rather than failing a finished call: its own
    lifetime limit (the same timeout) destroys it anyway.
    """
    with anyio.move_on_after(timeout_seconds, shield=True) as scope:
        try:
            await sandbox.close()
        except SandboxError as cause:
            logger.warning("sandbox.close_failed error=%s", type(cause.__cause__ or cause).__name__)
    if scope.cancelled_caught:
        logger.warning("sandbox.close_failed error=timeout")
