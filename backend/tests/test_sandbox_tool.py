"""run_python's behaviour: a fresh sandbox per call that is always closed,
workspace files in and out within the limits, and a bounded report.

Every test uses the in-memory sandbox from sandbox_fakes: no network, no key.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import anyio
import pytest
from langchain_core.tools import BaseTool

from api.services.toolbox.code_runner import TRUNCATED_NOTE, CodeRunner
from api.services.toolbox.sandbox import CodeError, CodeExecution, SandboxLimits, run_in_sandbox
from api.services.toolbox.tools import run_python_tool
from api.services.toolbox.workspace import LocalWorkspace, WorkspaceLimits
from tests.sandbox_fakes import FakeSandbox, Opener, call

LIMITS = SandboxLimits(timeout_seconds=5.0, max_files=3, max_file_bytes=100, max_output_chars=500)
WORKSPACE_LIMITS = WorkspaceLimits(100, 500, 20, 10, 5)
NOW = datetime(2026, 10, 24, 21, 30, tzinfo=timezone.utc)
FOLDER = "sandbox/20261024T213000.000000Z"


def run_python(root: Path, opener: Opener, limits: SandboxLimits = LIMITS) -> BaseTool:
    workspace = LocalWorkspace(root, WORKSPACE_LIMITS)
    return run_python_tool(CodeRunner(opener, workspace, limits, lambda: NOW))


@pytest.mark.asyncio
async def test_run_python_reports_the_run_and_saves_its_files(tmp_path: Path) -> None:
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "sales.csv").write_bytes(b"total\n42\n")
    sandbox = FakeSandbox(
        CodeExecution(stdout="total 42\n", result="42", charts=(b"\x89PNG chart",)),
        {"summary.csv": b"total,42\n", "nested/notes.txt": b"done"},
    )

    message = await call(
        run_python(tmp_path, Opener(sandbox)), code="run()", input_files=["data/sales.csv"]
    )

    assert message.status == "success"
    assert message.content == (
        f"Saved to the workspace:\n{FOLDER}/chart-1.png\n{FOLDER}/nested/notes.txt\n"
        f"{FOLDER}/summary.csv\n\nResult:\n42\n\nStdout:\ntotal 42"
    )
    assert sandbox.uploads == {"data/sales.csv": b"total\n42\n"}
    assert sandbox.codes == ["run()"]
    assert sandbox.closed
    assert (tmp_path / FOLDER / "chart-1.png").read_bytes() == b"\x89PNG chart"
    assert (tmp_path / FOLDER / "nested" / "notes.txt").read_bytes() == b"done"


@pytest.mark.asyncio
async def test_every_call_gets_a_fresh_sandbox(tmp_path: Path) -> None:
    opener = Opener()
    tool = run_python(tmp_path, opener)

    await call(tool, code="x = 1")
    await call(tool, code="print(x)")

    assert len(opener.opened) == 2
    assert opener.opened[0] is not opener.opened[1]
    assert all(sandbox.closed for sandbox in opener.opened)


@pytest.mark.asyncio
async def test_an_error_raised_by_the_code_is_an_error_result_with_a_short_traceback(
    tmp_path: Path,
) -> None:
    traceback = "\n".join(
        [
            "\x1b[0;31m-----------------------------------------------\x1b[0m",
            *(f"frame {number}" for number in range(1, 30)),
            "\x1b[0;31mZeroDivisionError\x1b[0m: division by zero",
        ]
    )
    error = CodeError("ZeroDivisionError", "division by zero", traceback)
    sandbox = FakeSandbox(CodeExecution(stdout="before\n", error=error))

    message = await call(run_python(tmp_path, Opener(sandbox)), code="1 / 0")

    content = str(message.content)
    lines = content.splitlines()
    assert message.status == "error"
    assert lines[:2] == ["Error: ZeroDivisionError: division by zero", "Traceback (last lines):"]
    assert "frame 29" in lines
    assert "frame 1" not in lines
    assert "\x1b" not in content
    assert content.endswith("Stdout:\nbefore")
    assert sandbox.closed


@pytest.mark.asyncio
async def test_a_run_over_the_timeout_is_an_error_result_and_still_closed(
    tmp_path: Path,
) -> None:
    sandbox = FakeSandbox(delay=5)
    limits = replace(LIMITS, timeout_seconds=0.05)

    message = await call(run_python(tmp_path, Opener(sandbox), limits), code="while True: pass")

    assert message.status == "error"
    assert "did not finish within 0.05 seconds" in str(message.content)
    assert sandbox.closed


@pytest.mark.asyncio
async def test_the_report_is_cut_at_the_output_limit_and_the_error_stays_visible(
    tmp_path: Path,
) -> None:
    error = CodeError("ValueError", "bad row", "ValueError: bad row")
    sandbox = FakeSandbox(CodeExecution(stdout="x" * 5_000, error=error))

    message = await call(run_python(tmp_path, Opener(sandbox)), code="parse()")

    content = str(message.content)
    assert content.startswith("Error: ValueError: bad row")
    assert content.endswith(TRUNCATED_NOTE)
    assert len(content) == LIMITS.max_output_chars + len(TRUNCATED_NOTE)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "reason"),
    [
        ("../outside.txt", "relative to the workspace"),
        (".env", "relative to the workspace"),
        ("/etc/passwd", "relative to the workspace"),
        ("missing.csv", "does not exist"),
        ("big.csv", "larger than the configured limit"),
    ],
)
async def test_input_files_are_confined_to_the_workspace_and_its_limits(
    tmp_path: Path, path: str, reason: str
) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    (tmp_path / "outside.txt").write_text("secret")
    (root / ".env").write_text("KEY=secret")
    (root / "big.csv").write_bytes(b"x" * (WORKSPACE_LIMITS.max_file_bytes + 1))
    opener = Opener()

    message = await call(run_python(root, opener), code="read()", input_files=[path])

    assert message.status == "error"
    assert reason in str(message.content)
    assert opener.opened == []


@pytest.mark.asyncio
async def test_too_many_input_files_are_refused_before_a_sandbox_starts(tmp_path: Path) -> None:
    for number in range(4):
        (tmp_path / f"{number}.csv").write_text("a\n")
    opener = Opener()

    message = await call(
        run_python(tmp_path, opener), code="read()", input_files=[f"{n}.csv" for n in range(4)]
    )

    assert message.status == "error"
    assert "at most 3 input files" in str(message.content)
    assert opener.opened == []


@pytest.mark.asyncio
async def test_only_files_within_the_count_and_size_limits_are_downloaded(
    tmp_path: Path,
) -> None:
    outputs = {
        "a.txt": b"a",
        "b.txt": b"b",
        "big.bin": b"x" * (LIMITS.max_file_bytes + 1),
        "c.txt": b"c",
        "d.txt": b"d",
    }
    sandbox = FakeSandbox(CodeExecution(), outputs)

    message = await call(run_python(tmp_path, Opener(sandbox)), code="write()")

    assert sandbox.downloads == ["a.txt", "b.txt", "c.txt"]
    assert sorted(path.name for path in (tmp_path / FOLDER).iterdir()) == [
        "a.txt",
        "b.txt",
        "c.txt",
    ]
    assert "Not saved (over the 3-file or 100-byte limit):\nbig.bin, d.txt" in str(message.content)


@pytest.mark.asyncio
async def test_saved_outputs_never_overwrite_or_leave_the_workspace(tmp_path: Path) -> None:
    opener = Opener(
        FakeSandbox(CodeExecution(), {"report.csv": b"first"}),
        FakeSandbox(CodeExecution(), {"report.csv": b"second", ".hidden": b"x"}),
    )
    tool = run_python(tmp_path, opener)

    await call(tool, code="write()")
    message = await call(tool, code="write()")  # same clock: the same folder

    assert (tmp_path / FOLDER / "report.csv").read_bytes() == b"first"
    assert not (tmp_path / FOLDER / ".hidden").exists()
    content = str(message.content)
    assert "report.csv: The artifact already exists; choose a new path." in content
    assert ".hidden: Use a visible path relative to the workspace." in content


@pytest.mark.asyncio
@pytest.mark.parametrize("step", ["upload", "execute", "list_outputs", "download"])
async def test_a_failing_sandbox_is_an_error_result_and_always_closed(
    tmp_path: Path, step: str
) -> None:
    (tmp_path / "in.csv").write_text("a\n")
    sandbox = FakeSandbox(CodeExecution(), {"out.txt": b"x"}, fail_on=step)

    message = await call(run_python(tmp_path, Opener(sandbox)), code="go()", input_files=["in.csv"])

    assert message.status == "error"
    assert f"failed during {step}" in str(message.content)
    assert sandbox.closed


@pytest.mark.asyncio
async def test_a_cancelled_call_still_closes_its_sandbox() -> None:
    sandbox = FakeSandbox(delay=10)

    with anyio.move_on_after(0.05):
        await run_in_sandbox(Opener(sandbox), "slow()", [], LIMITS)

    assert sandbox.closed


@pytest.mark.asyncio
async def test_a_sandbox_that_cannot_be_closed_does_not_fail_a_finished_run(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger="api.services.toolbox.sandbox")
    sandbox = FakeSandbox(fail_on="close")

    message = await call(run_python(tmp_path, Opener(sandbox)), code="print('hello')")

    assert message.status == "success"
    assert message.content == "Stdout:\nhello"
    assert "sandbox.close_failed error=SandboxError" in caplog.text


@pytest.mark.asyncio
async def test_the_run_is_logged_without_its_code_or_output(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="api.services.toolbox.sandbox")
    sandbox = FakeSandbox(CodeExecution(stdout="secret output\n"))

    await call(run_python(tmp_path, Opener(sandbox)), code="print('secret code')")
    await call(
        run_python(tmp_path, Opener(FakeSandbox(delay=5)), replace(LIMITS, timeout_seconds=0.05)),
        code="print('secret code')",
    )

    messages = [
        record.getMessage()
        for record in caplog.records
        if record.name == "api.services.toolbox.sandbox"
    ]
    assert messages[0].startswith("sandbox.run outcome=ok inputs=0 files=0 duration_ms=")
    assert messages[1].startswith("sandbox.run outcome=timeout error=TimeoutError duration_ms=")
    assert "secret" not in caplog.text
