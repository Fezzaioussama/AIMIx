"""In-memory stand-ins for the CodeSandbox port, shared by the run_python tests.

No network and no E2B key: the E2B adapter itself is covered against a fake of
the SDK in test_e2b_sandbox.py.
"""

from __future__ import annotations

from typing import Any

import anyio
from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool

from api.services.toolbox.sandbox import CodeExecution, OutputEntry, SandboxError, SandboxFile
from tests.conftest import tool_call


class FakeSandbox:
    """The CodeSandbox port in memory, recording how it was used."""

    def __init__(
        self,
        execution: CodeExecution | None = None,
        outputs: dict[str, bytes] | None = None,
        *,
        delay: float = 0.0,
        fail_on: str = "",
    ) -> None:
        self.execution = execution or CodeExecution(stdout="hello\n")
        self.outputs = outputs or {}
        self.delay = delay
        self.fail_on = fail_on
        self.uploads: dict[str, bytes] = {}
        self.codes: list[str] = []
        self.downloads: list[str] = []
        self.closed = False

    def _fail_if(self, step: str) -> None:
        if self.fail_on == step:
            raise SandboxError(f"The code sandbox failed during {step}.")

    async def upload(self, file: SandboxFile) -> None:
        self._fail_if("upload")
        self.uploads[file.path] = file.content

    async def execute(self, code: str) -> CodeExecution:
        self._fail_if("execute")
        self.codes.append(code)
        await anyio.sleep(self.delay)
        return self.execution

    async def list_outputs(self) -> list[OutputEntry]:
        self._fail_if("list_outputs")
        return [OutputEntry(path, len(content)) for path, content in self.outputs.items()]

    async def download(self, path: str) -> bytes:
        self._fail_if("download")
        self.downloads.append(path)
        return self.outputs[path]

    async def close(self) -> None:
        await anyio.sleep(0)  # a checkpoint: an unshielded close is cancelled here
        self._fail_if("close")
        self.closed = True


class Opener:
    """A SandboxOpener handing out one fake per call; it remembers each of them."""

    def __init__(self, *sandboxes: FakeSandbox) -> None:
        self._waiting = list(sandboxes)
        self.opened: list[FakeSandbox] = []

    async def __call__(self) -> FakeSandbox:
        sandbox = self._waiting.pop(0) if self._waiting else FakeSandbox()
        self.opened.append(sandbox)
        return sandbox


async def call(tool: BaseTool, **args: Any) -> ToolMessage:
    """Invoke run_python the way an agent does, so failures become messages."""
    message = await tool.ainvoke(tool_call("run_python", args))
    assert isinstance(message, ToolMessage)
    return message
