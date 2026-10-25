"""Run code in an isolated sandbox: the port, its value objects and the
lifecycle of one call (AGENTS.md §7 Adapter port; the E2B adapter lives in
``e2b_sandbox.py``).

Every call gets a fresh sandbox that is destroyed afterwards — after success,
after an error or a timeout, and when the agent itself is cancelled — so no
state or user data outlives the call. One deadline, SANDBOX_TIMEOUT_SECONDS,
covers the whole call: creating the sandbox, uploading the inputs, running the
code and collecting its files. It starts before the sandbox exists, so it
always ends before the sandbox's own lifetime (the same timeout) does.

Creating the sandbox is shielded from that deadline and from cancellation: a
creation cut short could leave a sandbox running, and billed, that nothing
would close. It finishes (bounded by the opener's own request timeout, and at
most OPEN_GRACE_FACTOR deadlines here), then the call stops and closes it.

Failures raise ``SandboxError``, a ``ToolException``: the agent receives it as
an error result it can react to.
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
#: Where a call's files go, relative to its folder: separate, so never colliding.
CHARTS_FOLDER = "charts"
OUTPUTS_FOLDER = "outputs"
#: A shielded creation is still abandoned after this many SANDBOX_TIMEOUT_SECONDS.
OPEN_GRACE_FACTOR = 2


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
    #: ``charts/chart-<n>.png``, then ``outputs/<path>``, within the limits.
    files: tuple[SandboxFile, ...] = ()
    #: Files left behind for exceeding the file count or size limit.
    skipped: tuple[str, ...] = ()
    #: Files that could not be downloaded, as ``"<path>: <reason>"``.
    failed: tuple[str, ...] = ()


class CodeSandbox(Protocol):
    """One fresh, isolated sandbox, used for a single call and then closed."""

    async def upload(self, file: SandboxFile) -> None:
        """Make ``file`` readable by the code at INPUT_DIR/<path>."""

    async def execute(self, code: str) -> CodeExecution:
        """Run Python code. An exception it raises is reported, not raised."""

    async def list_outputs(self) -> list[OutputEntry]:
        """The regular files below OUTPUT_DIR, with paths relative to it."""

    async def download(self, path: str, max_bytes: int) -> bytes:
        """OUTPUT_DIR/<path>; raise ``SandboxError`` once it exceeds ``max_bytes``."""

    async def close(self) -> None:
        """Destroy the sandbox and everything in it."""


#: Opens a new sandbox for every call (Factory).
SandboxOpener = Callable[[], Awaitable[CodeSandbox]]


def metered(open_sandbox: SandboxOpener, spend: Callable[[], None]) -> SandboxOpener:
    """``open_sandbox`` that first calls ``spend`` (Decorator): a per-user
    allowance that raises ``ToolException`` once used up, so no sandbox is
    created. ``spend`` may touch the database, so it runs in a worker thread."""

    async def open_metered() -> CodeSandbox:
        await anyio.to_thread.run_sync(spend)
        return await open_sandbox()

    return open_metered


@dataclass(frozen=True)
class _Candidate:
    #: Where the file goes, relative to the call's folder.
    path: str
    size: int
    #: A chart is already in memory; an output is downloaded from ``source``.
    content: bytes | None = None
    source: str = ""


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
    sandbox: CodeSandbox | None = None
    try:
        with anyio.fail_after(limits.timeout_seconds):
            sandbox = await _open(open_sandbox, limits.timeout_seconds)
            run = await _use(sandbox, code, inputs, limits)
    except TimeoutError as cause:
        raise SandboxTimedOut(
            f"The code did not finish within {limits.timeout_seconds:g} seconds."
        ) from cause
    finally:
        if sandbox is not None:  # outside the deadline: closing must not be cut short
            await _close(sandbox, limits.timeout_seconds)
    return run


async def _open(open_sandbox: SandboxOpener, timeout_seconds: float) -> CodeSandbox:
    """Create the sandbox even when the deadline passes or the agent is
    cancelled meanwhile, so the caller holds it and can close it."""
    with anyio.CancelScope(shield=True), anyio.fail_after(OPEN_GRACE_FACTOR * timeout_seconds):
        sandbox = await open_sandbox()
    return sandbox  # noqa: RET504 - inside the scope, mypy sees a path with no return


async def _use(
    sandbox: CodeSandbox, code: str, inputs: Sequence[SandboxFile], limits: SandboxLimits
) -> SandboxRun:
    for item in inputs:
        await sandbox.upload(item)
    execution = await sandbox.execute(code)
    candidates = [
        _Candidate(f"{CHARTS_FOLDER}/chart-{number}.png", len(png), content=png)
        for number, png in enumerate(execution.charts, start=1)
    ]
    outputs = sorted(await sandbox.list_outputs(), key=attrgetter("path"))
    candidates += [
        _Candidate(f"{OUTPUTS_FOLDER}/{entry.path}", entry.size, source=entry.path)
        for entry in outputs
    ]
    fitting = [item for item in candidates if item.size <= limits.max_file_bytes]
    too_large = [item.path for item in candidates if item.size > limits.max_file_bytes]
    over_count = [item.path for item in fitting[limits.max_files :]]
    files, failed = await _download(sandbox, fitting[: limits.max_files], limits.max_file_bytes)
    return SandboxRun(execution, tuple(files), (*too_large, *over_count), tuple(failed))


async def _download(
    sandbox: CodeSandbox, kept: Sequence[_Candidate], max_bytes: int
) -> tuple[list[SandboxFile], list[str]]:
    """Fetch what was kept; a file that cannot be fetched is reported, not fatal."""
    files: list[SandboxFile] = []
    failed: list[str] = []
    for item in kept:
        try:
            content = item.content
            if content is None:
                content = await sandbox.download(item.source, max_bytes)
        except SandboxTimedOut:
            raise
        except SandboxError as cause:
            failed.append(f"{item.path}: {cause}")
        else:
            files.append(SandboxFile(item.path, content))
    return files, failed


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
