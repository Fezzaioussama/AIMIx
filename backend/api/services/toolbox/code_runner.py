"""``run_python``: agent-written code in a fresh sandbox, with workspace files
going in and coming back out.

Input files are read through ``LocalWorkspace`` (confined, size-limited) and
outputs are saved through it (no overwrites) into a new ``sandbox/<UTC time>/``
folder. Disk work runs in a worker thread, so the agent's event loop never
blocks on it.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from functools import partial
from pathlib import PurePosixPath

import anyio
from langchain_core.tools import ToolException

from api.services.toolbox.sandbox import (
    CodeError,
    SandboxFile,
    SandboxLimits,
    SandboxOpener,
    SandboxRun,
    run_in_sandbox,
)
from api.services.toolbox.workspace import LocalWorkspace

#: Workspace folder that receives each call's files, one subfolder per call.
OUTPUT_FOLDER = "sandbox"
#: Only the end of a traceback is kept: the frame that failed and the error.
TRACEBACK_LINES = 15
TRUNCATED_NOTE = "\n\n[Truncated: the output continues beyond this point.]"
_ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def _plain(text: str) -> str:
    """Drop the terminal colour codes Jupyter puts in tracebacks and logs."""
    return _ANSI_ESCAPE.sub("", text).strip()


def _section(title: str, body: str) -> str:
    return f"{title}:\n{body}" if body else ""


def _error_section(error: CodeError | None) -> str:
    if error is None:
        return ""
    lines = _plain(error.traceback).splitlines()[-TRACEBACK_LINES:]
    header = f"Error: {error.name}: {_plain(error.value)}"
    return "\n".join([header, "Traceback (last lines):", *lines]) if lines else header


def _listed(paths: Sequence[str], shown: int) -> str:
    """At most ``shown`` paths, so a flood of files cannot crowd out the output."""
    extra = len(paths) - shown
    return ", ".join(paths[:shown]) + (f" and {extra} more" if extra > 0 else "")


def _report(
    run: SandboxRun, saved: Sequence[str], refused: Sequence[str], limits: SandboxLimits
) -> str:
    """The agent's view of a run, errors and files first, cut at the output limit."""
    execution = run.execution
    sections = (
        _error_section(execution.error),
        _section("Saved to the workspace", "\n".join(saved)),
        _section("Not saved", "\n".join([*run.failed, *refused])),
        _section(
            f"Not saved (over the {limits.max_files}-file or {limits.max_file_bytes}-byte limit)",
            _listed(run.skipped, limits.max_files),
        ),
        _section("Result", _plain(execution.result)),
        _section("Stdout", _plain(execution.stdout)),
        _section("Stderr", _plain(execution.stderr)),
    )
    text = "\n\n".join(part for part in sections if part) or "The code ran and printed nothing."
    limit = limits.max_output_chars
    return text if len(text) <= limit else text[:limit] + TRUNCATED_NOTE


class CodeRunner:
    """Run Python in a fresh sandbox per call, with workspace files in and out."""

    def __init__(
        self,
        open_sandbox: SandboxOpener,
        workspace: LocalWorkspace,
        limits: SandboxLimits,
        clock: Callable[[], datetime] = partial(datetime.now, timezone.utc),
    ) -> None:
        self._open_sandbox = open_sandbox
        self._workspace = workspace
        self._limits = limits
        self._clock = clock

    async def run(self, code: str, input_files: list[str] | None = None) -> str:
        """Return the report; raise it as a ``ToolException`` if the code failed."""
        if not code.strip():
            raise ToolException("Pass the Python code to run.")
        inputs = await anyio.to_thread.run_sync(self._read_inputs, input_files or [])
        folder = f"{OUTPUT_FOLDER}/{self._clock():%Y%m%dT%H%M%S.%fZ}"
        run = await run_in_sandbox(self._open_sandbox, code, inputs, self._limits)
        saved, refused = await anyio.to_thread.run_sync(self._save, folder, run.files)
        text = _report(run, saved, refused, self._limits)
        if run.execution.error is not None:
            raise ToolException(text)
        return text

    def _read_inputs(self, paths: list[str]) -> list[SandboxFile]:
        unique = list(dict.fromkeys(paths))
        if len(unique) > self._limits.max_files:
            raise ToolException(f"Pass at most {self._limits.max_files} input files.")
        files = []
        for path in unique:
            content = self._workspace.read_bytes(path)  # confined and size-checked
            files.append(SandboxFile(PurePosixPath(path).as_posix(), content))
        return files

    def _save(self, folder: str, files: Sequence[SandboxFile]) -> tuple[list[str], list[str]]:
        saved: list[str] = []
        refused: list[str] = []
        for item in files:
            try:
                saved.append(self._workspace.save_bytes(f"{folder}/{item.path}", item.content))
            except ToolException as cause:
                refused.append(f"{item.path}: {cause}")
        return saved, refused
