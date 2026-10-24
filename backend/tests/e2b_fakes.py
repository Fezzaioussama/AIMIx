"""In-memory stand-ins for the e2b-code-interpreter SDK sandbox, so the E2B
adapter is tested with no network and no key. Results are the SDK's own data
classes, so a change in their shape fails a test rather than production."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any

from e2b import EntryInfo, FileType
from e2b_code_interpreter import Execution, OutputMessage

from api.services.toolbox.e2b_sandbox import E2BSandbox, E2BSandboxOpener

KEY = "e2b-test-key"


def entry(path: str, kind: FileType, size: int = 0) -> EntryInfo:
    """A listing entry as the SDK returns it."""
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
    """The SDK's streamed download: an async context manager over 4-byte chunks."""

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
    """``sandbox.files``: records writes and serves listings and downloads."""

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
    """The SDK's AsyncSandbox: replays ``execution`` and records what it is asked."""

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
