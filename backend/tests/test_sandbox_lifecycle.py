"""run_python's lifecycle guarantees: a fresh sandbox per call, always closed
(after success, errors, timeouts and cancellation), one deadline for the whole
call, and a boundary log without the code or its output.

Every test uses the in-memory sandbox from sandbox_fakes: no network, no key.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from pathlib import Path

import anyio
import pytest

from api.services.toolbox.sandbox import CodeExecution, SandboxTimedOut, run_in_sandbox
from tests.sandbox_fakes import LIMITS, FakeSandbox, Opener, call, run_python


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
async def test_the_deadline_covers_creating_the_sandbox() -> None:
    async def slow_opener() -> FakeSandbox:
        await anyio.sleep(5)
        return FakeSandbox()

    with pytest.raises(SandboxTimedOut, match=r"within 0\.05 seconds"):
        await run_in_sandbox(slow_opener, "go()", [], replace(LIMITS, timeout_seconds=0.05))


@pytest.mark.asyncio
@pytest.mark.parametrize("step", ["upload", "execute", "list_outputs"])
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
async def test_a_download_that_times_out_still_fails_the_call(tmp_path: Path) -> None:
    class SlowDownloads(FakeSandbox):
        async def download(self, path: str, max_bytes: int) -> bytes:
            raise SandboxTimedOut("The code sandbox timed out.")

    sandbox = SlowDownloads(CodeExecution(), {"out.txt": b"x"})

    message = await call(run_python(tmp_path, Opener(sandbox)), code="go()")

    assert message.status == "error"
    assert "timed out" in str(message.content)
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


class SlowCreation:
    """An opener whose sandbox exists at once (E2B started it) while the answer
    takes ``seconds`` to arrive."""

    def __init__(self, seconds: float) -> None:
        self.seconds = seconds
        self.created: list[FakeSandbox] = []

    async def __call__(self) -> FakeSandbox:
        sandbox = FakeSandbox()
        self.created.append(sandbox)
        await anyio.sleep(self.seconds)
        return sandbox


@pytest.mark.asyncio
async def test_a_sandbox_still_being_created_at_the_deadline_is_closed() -> None:
    opener = SlowCreation(0.15)

    with pytest.raises(SandboxTimedOut, match=r"within 0\.1 seconds"):
        await run_in_sandbox(opener, "go()", [], replace(LIMITS, timeout_seconds=0.1))

    assert [sandbox.closed for sandbox in opener.created] == [True]


@pytest.mark.asyncio
async def test_a_sandbox_being_created_when_the_agent_is_cancelled_is_closed() -> None:
    opener = SlowCreation(0.1)

    with anyio.move_on_after(0.02) as scope:
        await run_in_sandbox(opener, "go()", [], LIMITS)

    assert scope.cancelled_caught
    assert [sandbox.closed for sandbox in opener.created] == [True]
