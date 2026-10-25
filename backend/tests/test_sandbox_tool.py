"""run_python's output: the report the agent reads, and workspace files going in
and coming back out within the limits (the lifecycle is in
test_sandbox_lifecycle.py).

Every test uses the in-memory sandbox from sandbox_fakes: no network, no key.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from api.services.toolbox.code_runner import TRUNCATED_NOTE
from api.services.toolbox.sandbox import CodeError, CodeExecution
from tests.sandbox_fakes import (
    FOLDER,
    LIMITS,
    WORKSPACE_LIMITS,
    FakeSandbox,
    Opener,
    call,
    run_python,
)


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
        f"Saved to the workspace:\n{FOLDER}/charts/chart-1.png\n"
        f"{FOLDER}/outputs/nested/notes.txt\n{FOLDER}/outputs/summary.csv\n\n"
        "Result:\n42\n\nStdout:\ntotal 42"
    )
    assert sandbox.uploads == {"data/sales.csv": b"total\n42\n"}
    assert sandbox.codes == ["run()"]
    assert sandbox.closed
    assert (tmp_path / FOLDER / "charts" / "chart-1.png").read_bytes() == b"\x89PNG chart"
    assert (tmp_path / FOLDER / "outputs" / "nested" / "notes.txt").read_bytes() == b"done"


@pytest.mark.asyncio
async def test_a_chart_and_an_output_with_the_same_name_are_both_saved(tmp_path: Path) -> None:
    sandbox = FakeSandbox(CodeExecution(charts=(b"shown",)), {"chart-1.png": b"saved"})

    await call(run_python(tmp_path, Opener(sandbox)), code="plot()")

    assert (tmp_path / FOLDER / "charts" / "chart-1.png").read_bytes() == b"shown"
    assert (tmp_path / FOLDER / "outputs" / "chart-1.png").read_bytes() == b"saved"


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
        ("linked.csv", "Links are not followed"),  # a visible link to a hidden file
        ("missing.csv", "does not exist"),
        ("big.csv", "larger than the configured limit"),
    ],
)
async def test_input_files_are_confined_to_the_workspace_and_its_limits(
    tmp_path: Path, path: str, reason: str
) -> None:
    root = tmp_path / "workspace"
    (root / ".secrets").mkdir(parents=True)
    (tmp_path / "outside.txt").write_text("secret")
    (root / ".env").write_text("KEY=secret")
    (root / ".secrets" / "key.csv").write_text("secret")
    (root / "linked.csv").symlink_to(root / ".secrets" / "key.csv")
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
    assert sorted(path.name for path in (tmp_path / FOLDER / "outputs").iterdir()) == [
        "a.txt",
        "b.txt",
        "c.txt",
    ]
    assert "Not saved (over the 3-file or 100-byte limit):\noutputs/big.bin, outputs/d.txt" in str(
        message.content
    )


@pytest.mark.asyncio
async def test_a_file_that_cannot_be_downloaded_is_reported_and_the_run_kept(
    tmp_path: Path,
) -> None:
    sandbox = FakeSandbox(CodeExecution(stdout="done\n"), {"a.txt": b"a", "log.txt": b"x" * 500})
    sandbox.listed_sizes["log.txt"] = 1  # still growing after the listing

    message = await call(run_python(tmp_path, Opener(sandbox)), code="write()")

    assert message.status == "success"
    assert message.content == (
        f"Saved to the workspace:\n{FOLDER}/outputs/a.txt\n\n"
        "Not saved:\noutputs/log.txt: The file grew beyond the 100-byte limit.\n\n"
        "Stdout:\ndone"
    )


@pytest.mark.asyncio
async def test_saved_outputs_never_overwrite_or_leave_the_workspace(tmp_path: Path) -> None:
    opener = Opener(
        FakeSandbox(CodeExecution(), {"report.csv": b"first"}),
        FakeSandbox(CodeExecution(), {"report.csv": b"second", ".hidden": b"x"}),
    )
    tool = run_python(tmp_path, opener)

    await call(tool, code="write()")
    message = await call(tool, code="write()")  # same clock: the same folder

    assert (tmp_path / FOLDER / "outputs" / "report.csv").read_bytes() == b"first"
    assert not (tmp_path / FOLDER / "outputs" / ".hidden").exists()
    content = str(message.content)
    assert f"outputs/report.csv: '{FOLDER}/outputs/report.csv' already exists" in content
    assert "outputs/.hidden: Use a visible path relative to the workspace." in content


@pytest.mark.asyncio
async def test_a_csv_the_code_writes_cannot_run_formulas_in_a_spreadsheet(
    tmp_path: Path,
) -> None:
    outputs = {
        "leads.csv": b'name,site\nacme,=HYPERLINK("evil.example")\n',
        "plain.csv": "\ufeffname,total\nzoë,-12.5\n".encode(),
        "latin.csv": "name;note\ncafé;@SUM(1)\n".encode("latin-1"),
    }
    sandbox = FakeSandbox(CodeExecution(), outputs)

    message = await call(run_python(tmp_path, Opener(sandbox)), code="export()")

    assert message.status == "success"
    saved = tmp_path / FOLDER / "outputs"
    assert (saved / "leads.csv").read_text() == (
        '"name","site"\n"acme","\'=HYPERLINK(""evil.example"")"\n'
    )
    assert (saved / "plain.csv").read_bytes() == outputs["plain.csv"]  # nothing to change
    assert (saved / "latin.csv").read_text() == '"name";"note"\n"café";"\'@SUM(1)"\n'
